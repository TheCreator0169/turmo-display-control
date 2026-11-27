"""Theme Editor (v0.2.3): the widget data classes and the visual editor. It was the middle of turmo_app_enhanced.py;
the app re-exports these names, so `app.ThemeEditor` and `app.WidgetConfig` keep working."""

from scripts.gui_common import *  # noqa: F401,F403

# ─── Theme Editor Data Structures ───

@dataclass
class WidgetConfig:
    """Configuration for a single widget in the theme."""
    id: str
    type: str
    x: int
    y: int
    w: int = 0
    h: int = 0
    sensor: str = ""
    format: str = ""
    font_size: int = 12
    color: str = "#ffffff"
    background: str = ""
    thickness: int = 0
    text: str = ""
    align: str = "left"
    color_rules: List[Dict] = None
    extra: Dict = None  # every other key of the widget in theme.json (icon, size, glow, font...), kept as it was
    keys: set = None  # the keys the file had or the user set: only those are written back

    def __post_init__(self):
        if self.keys is None:
            self.keys = set()
        if self.color_rules is None:
            self.color_rules = []
        if self.extra is None:
            self.extra = {}


def tk_colour(colour: str) -> str:
    """Tk has no alpha: a palette entry "#rrggbbaa" is shown as "#rrggbb"."""
    return colour[:7] if colour.startswith("#") and len(colour) == 9 else colour


@dataclass
class ThemePalette:
    """Theme color palette."""
    colors: Dict[str, str]

    def get(self, key: str, default: str = "#000000") -> str:
        """Resolve color reference (e.g., @accent) or return hex."""
        if key.startswith("@"):
            return self.colors.get(key[1:], default)
        return key


WIDGET_FIELDS = ("id", "type", "x", "y", "w", "h", "sensor", "format", "font_size", "color", "background",
                 "thickness", "text", "align", "color_rules")
SIZED_TYPES = ("rect", "gauge", "bar", "graph")


def widget_defaults(wtype):
    """What the renderer assumes for a widget of this type when the file says nothing (font size, colour...)."""
    try:
        from libre_panel.theme.model import normalize_widget
        return normalize_widget({"type": wtype, "id": "x"}, 0)[0]
    except Exception as _e:
        log_swallowed("theme palette load", _e)
        return {}


def widget_from_dict(wdata):
    """A WidgetConfig from a theme.json widget. Keys the file does not have show the renderer's defaults; keys the
    editor has no field for are kept in `extra`, so saving the theme loses nothing."""
    d = widget_defaults(wdata.get("type", ""))

    def get(key, fallback):
        return wdata.get(key, d.get(key, fallback))
    return WidgetConfig(
        id=wdata.get("id", ""), type=wdata.get("type", ""), x=wdata.get("x", 0), y=wdata.get("y", 0),
        w=wdata.get("w", 0), h=wdata.get("h", 0), sensor=get("sensor", ""), format=get("format", ""),
        font_size=get("font_size", 12), color=get("color", "#ffffff"), background=wdata.get("background", ""),
        thickness=get("thickness", 0), text=get("text", ""), align=get("align", "left"),
        color_rules=wdata.get("color_rules", []),
        extra={k: v for k, v in wdata.items() if k not in WIDGET_FIELDS},
        keys={k for k in wdata if k in WIDGET_FIELDS})


def widget_to_dict(w):
    """The theme.json widget for a WidgetConfig: its extra keys, then the fields the file had or the user set."""
    out = dict(w.extra)
    out.update(id=w.id, type=w.type)
    if w.x or w.y or {"x", "y"} & w.keys:  # a grid widget (module) has no x and y
        out.update(x=w.x, y=w.y)
    if w.type in SIZED_TYPES or w.w or w.h or {"w", "h"} & w.keys:
        out.update(w=w.w, h=w.h)
    for key in ("sensor", "format", "font_size", "color", "background", "thickness", "text", "align"):
        if key in w.keys:
            out[key] = getattr(w, key)
    if w.color_rules:
        out["color_rules"] = w.color_rules
    return out


class ThemeEditor:
    """Visual drag-and-drop theme editor."""

    @property
    def theme_name(self):
        return self._theme_name

    @theme_name.setter
    def theme_name(self, value):  # loading or saving another theme ends a New theme draft
        self._theme_name = value
        self._draft = False

    def __init__(self, parent_app, canvas_frame: ttk.Frame):
        self.app = parent_app
        self.canvas_frame = canvas_frame
        self.settings = parent_app.settings
        self.theme_name = self.settings.theme
        self.widgets: List[WidgetConfig] = []
        self.selected_widget: Optional[WidgetConfig] = None
        self._boxes = []  # (widget, on-screen box), filled by redraw_canvas
        self._doc, self._locked, self._cache = None, [], {}  # the theme document the renderer draws from
        self.drag_data = {"x": 0, "y": 0, "widget": None}
        self.preview_scale = 1.0

        # Palette from current theme
        self._pending_palette = None  # the palette of an imported file, written on the next save
        self._stash = {}  # (theme, orientation) -> the widgets being edited, kept while the other one is shown
        self._shown = "landscape" if parent_app.settings.orientation == "landscape" else "portrait"
        self.palette = self.load_palette()

        self.build_editor_ui()
        self.load_current_theme()
        if not is_editable_theme(self.theme_name):  # a built-in theme is applied: the editor opens a new theme
            self.start_draft()

    def follow(self, theme):
        """The applied theme changed: the editor shows it if it is the user's (or the Custom Blank Canvas). A
        built-in theme is never loaded for editing; the editor keeps what it has."""
        if is_editable_theme(theme):
            self.theme_name = theme
            self.load_current_theme()

    def current_orientation(self) -> str:
        var = getattr(self, "editor_orientation", None)
        return var.get() if var is not None else self._shown

    def theme_dir(self, orientation=None) -> Path:
        """Folder of the theme for an orientation: <name> is landscape, <name>-320x480 is portrait."""
        base = theme_paths.folder(DATA_ROOT / "themes", self.theme_name)
        portrait = theme_paths.folder(DATA_ROOT / "themes", f"{self.theme_name}-320x480")
        return portrait if (orientation or self.current_orientation()) == "portrait" and portrait.is_dir() else base

    def load_palette(self) -> ThemePalette:
        """Load palette from current theme."""
        theme_path = self.theme_dir() / "theme.json"
        if theme_path.exists():
            with open(theme_path, encoding="utf-8") as f:
                data = json.load(f)
            return ThemePalette(data.get("palette", {}))
        return ThemePalette({})

    def build_editor_ui(self):
        """Build the theme editor UI (v0.2.0 design): a header with the file actions, then three panes: the
        widget palette as tiles, the canvas under a caption bar, and the Properties card."""
        app = self.app
        bg0, bg2 = PALETTE["bg0"], PALETTE["bg2"]
        font, semi, small = (app.ui_font, 10), (app.ui_semibold, 11), (app.ui_font, 9)
        frame = self.canvas_frame

        head = page_header(frame, tr("Theme Editor"), tr("Drag widgets onto the canvas, then tune them."),
                           bg0, (app.ui_semibold, 16), (app.ui_font, 10))
        head.pack(fill=tk.X, padx=24, pady=(24, 0))
        for text, command in ((tr("Load theme"), self.load_theme_dialog), (tr("Export JSON"), self.export_json),
                              (tr("Import JSON"), self.import_json)):
            make_button(head.actions, text, command, font, variant="ghost", backdrop=bg0, small=True).pack(
                side=tk.LEFT, padx=(0, 6))
        make_button(head.actions, tr("Save theme"), self.save_theme, font, variant="primary", backdrop=bg0).pack(
            side=tk.LEFT)

        panes = tk.Frame(frame, bg=bg0)
        panes.pack(fill=tk.BOTH, expand=True, padx=24, pady=(16, 24))
        panes.rowconfigure(0, weight=1)
        panes.columnconfigure(0, minsize=self.app.px(230))
        panes.columnconfigure(1, weight=1)
        panes.columnconfigure(2, minsize=self.app.px(250))

        # Left: the widget palette as tiles
        left = RoundedCard(panes, bg2, PALETTE["line"], bg0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        # v0.3.8.2: the column scrolls when the window is short (1366x768 at 125 % and more left the list under 50 px)
        column = ScrollFrame(left.inner, bg2, stretch=True)
        column._canvas.configure(width=1)  # a Canvas asks for 378 px by default
        column.pack(fill=tk.BOTH, expand=True)
        tk.Label(column.body, text=tr("WIDGETS"), bg=bg2, fg=PALETTE["muted"], font=(app.ui_font, 8, "bold"),
                 anchor="w").pack(fill=tk.X, padx=14, pady=(14, 8))
        tiles = tk.Frame(column.body, bg=bg2)
        tiles.pack(fill=tk.X, padx=14, pady=(0, 14))
        tiles.columnconfigure(0, weight=1, uniform="tile")
        tiles.columnconfigure(1, weight=1, uniform="tile")
        widget_types = [
            ("\uE739", "Rect", "rect", "Card or fill"),
            ("\uE121", "Clock", "clock", "Time and date"),
            ("\uE8EF", "Metric", "metric", "Number + unit"),
            ("\uEC4A", "Gauge", "gauge", "Value ring"),
            ("\uE9D5", "Bar", "bar", "Progress bar"),
            ("\uE9D9", "Graph", "graph", "Sensor history"),
            ("\uE8D2", "Text", "text", "Static label"),
            ("\uE734", "Icon", "icon", "Round icon"),
        ]
        self._glyphs = {wtype: glyph for glyph, _label, wtype, _sub in widget_types}
        for i, (glyph, label, wtype, sub) in enumerate(widget_types):
            WidgetTile(tiles, glyph, tr(label), tr(sub), lambda t=wtype: self.add_widget(t), bg2, bg2, (ICON_FONT, 14),
                       (app.ui_semibold, 10), small).grid(row=i // 2, column=i % 2, sticky="ew",
                                                          padx=(0, 4) if i % 2 == 0 else (4, 0),
                                                          pady=(0, 8) if i < 6 else 0)

        # Under the palette: the widgets already in the theme, to pick one without hunting for it on the canvas
        tk.Frame(column.body, bg=PALETTE["line"], height=1).pack(fill=tk.X)
        self._layers_title = tk.Label(column.body, text=tr("IN THIS THEME"), bg=bg2, fg=PALETTE["muted"],
                                      font=(app.ui_font, 8, "bold"), anchor="w")
        self._layers_title.pack(fill=tk.X, padx=14, pady=(12, 8))
        self._layers = ScrollFrame(column.body, bg2)
        # width=1: a Canvas asks for 378 px by default, which widened the column. The height is the least the list
        # keeps (about three rows, what it has at the normal window size); the column above scrolls instead of squeezing it away.
        self._layers._canvas.configure(width=1, height=self.app.px(120))
        self._layers.pack(fill=tk.BOTH, expand=True, padx=(14, 6), pady=(0, 12))
        self._layers_sig = None

        # Centre: a caption bar (size, orientation, grid, zoom) over the canvas
        centre = RoundedCard(panes, bg0, PALETTE["line"], bg0)
        centre.grid(row=0, column=1, sticky="nsew", padx=(0, 16))
        self.editor_orientation = tk.StringVar(value=self._shown)
        self.show_grid = tk.BooleanVar(value=True)
        self.zoom_var = tk.DoubleVar(value=1.0)
        bar = tk.Frame(centre.inner, bg=bg0)  # two rows, so it fits the narrowest window
        bar.pack(fill=tk.X, padx=14, pady=(10, 4))
        self._caption = tk.Label(bar, text="", bg=bg0, fg=PALETTE["muted"], font=(app.ui_font, 8, "bold"))
        self._caption.pack(side=tk.LEFT)
        # the track starts Slider.PAD px inside its canvas: 12 px after the caption, then it runs to the right
        Slider(bar, 0.5, 2.0, 1.0, self.on_zoom_change, bg0, variable=self.zoom_var, step=0.1, width=90).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        bar2 = tk.Frame(centre.inner, bg=bg0)
        bar2.pack(fill=tk.X, padx=14, pady=(0, 10))
        orient = Segmented(bar2, [("landscape", tr("Landscape")), ("portrait", tr("Portrait"))], self._shown,
                           lambda _v: self.on_orientation_change(), bg0, small, variable=self.editor_orientation)
        orient.pack(side=tk.LEFT)
        natural = orient.winfo_reqwidth()
        # same left edge, grown to the middle of the panel
        bar2.bind("<Configure>", lambda e: orient.fit_width(max(natural, e.width // 2)))
        Switch(bar2, True, lambda _on: self.redraw_canvas(), bg0, variable=self.show_grid).pack(side=tk.RIGHT)
        tk.Label(bar2, text=tr("Grid"), bg=bg0, fg=PALETTE["muted"], font=small).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Frame(centre.inner, bg=PALETTE["line"], height=1).pack(fill=tk.X)
        self.editor_canvas = tk.Canvas(centre.inner, bg="#0a0118", highlightthickness=0, bd=0)
        self.editor_canvas.pack(fill=tk.BOTH, expand=True)
        self.editor_canvas.bind("<Button-1>", self.on_canvas_click)
        self.editor_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.editor_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.editor_canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        self.editor_canvas.bind("<Configure>", self.on_canvas_resize)

        # Right: the Properties card
        right = RoundedCard(panes, bg0, PALETTE["line"], bg0)
        right.grid(row=0, column=2, sticky="nsew")
        tk.Label(right.inner, text=tr("THEME NAME"), bg=bg0, fg=PALETTE["muted"], font=(app.ui_font, 8, "bold"),
                 anchor="w").pack(fill=tk.X, padx=14, pady=(14, 6))
        self.name_var = tk.StringVar(value=self.theme_name)
        self._named = self.theme_name
        rounded_entry(right.inner, self.name_var, bg0, (app.ui_font, 10))[0].pack(fill=tk.X, padx=14)
        tk.Label(right.inner, text=tr("PROPERTIES"), bg=bg0, fg=PALETTE["muted"], font=(app.ui_font, 8, "bold"),
                 anchor="w").pack(fill=tk.X, padx=14, pady=(16, 8))
        self.props_actions = tk.Frame(right.inner, bg=bg0)  # Duplicate and Delete: always in sight
        self.props_actions.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=(0, 14))
        # the bar is slim (10 px) and sits at the edge, 15 px from the fields, so the fields keep their width
        self.props_frame = ScrollFrame(right.inner, bg0, bar_gap=15)
        self.props_frame._canvas.configure(width=1)  # a Canvas asks for 378 px by default
        self.props_frame.pack(fill=tk.BOTH, expand=True, padx=(14, 4), pady=(0, 10))
        self.props_inner = self.props_frame.body
        self._props_for = None

    def _update_caption(self):
        tw, th = self.get_canvas_size()
        self._caption.config(text=f"{tw} \u00d7 {th}  \u00b7  {round(self.preview_scale * 100)}%")

    def get_canvas_size(self) -> tuple:
        """Get current canvas size based on orientation."""
        if self.editor_orientation.get() == "landscape":
            return LANDSCAPE_SIZE
        return TURING_SIZE

    def on_orientation_change(self):
        """Handle orientation change in editor: show the other orientation's widgets (edits to the one left
        stay in memory until saved)."""
        self._stash[(self.theme_name, self._shown)] = self.widgets
        self._shown = self.current_orientation()
        kept = self._stash.get((self.theme_name, self._shown))
        if kept is None:
            self.load_current_theme()
            return
        self.widgets, self.selected_widget = kept, None
        self.palette = self.load_palette()
        self.redraw_canvas()
        self.update_properties_panel()

    def on_zoom_change(self, val):
        """Handle zoom change."""
        self.preview_scale = float(val)
        self.redraw_canvas()

    def on_canvas_resize(self, event):
        """Handle canvas resize."""
        self.redraw_canvas()

    def canvas_to_theme_coords(self, x: int, y: int) -> tuple:
        """Convert canvas coordinates to theme coordinates."""
        cw = self.editor_canvas.winfo_width()
        ch = self.editor_canvas.winfo_height()
        tw, th = self.get_canvas_size()

        # Calculate scale to fit theme in canvas
        scale_x = cw / tw
        scale_y = ch / th
        scale = min(scale_x, scale_y) * self.preview_scale

        # Center offset
        offset_x = (cw - tw * scale) / 2
        offset_y = (ch - th * scale) / 2

        theme_x = (x - offset_x) / scale
        theme_y = (y - offset_y) / scale
        return theme_x, theme_y

    def theme_to_canvas_coords(self, x: int, y: int, w: int = 0, h: int = 0) -> tuple:
        """Convert theme coordinates to canvas coordinates."""
        cw = self.editor_canvas.winfo_width()
        ch = self.editor_canvas.winfo_height()
        tw, th = self.get_canvas_size()

        scale_x = cw / tw
        scale_y = ch / th
        scale = min(scale_x, scale_y) * self.preview_scale

        offset_x = (cw - tw * scale) / 2
        offset_y = (ch - th * scale) / 2

        cx = offset_x + x * scale
        cy = offset_y + y * scale
        cw_scaled = w * scale
        ch_scaled = h * scale
        return cx, cy, cw_scaled, ch_scaled

    def _shot(self):
        """The theme as the display draws it, from the widgets being edited; None if there is no theme document."""
        doc = getattr(self, "_doc", None)
        if not doc:
            return None
        from scripts import shape_icons
        shape_icons.register()
        if self._pending_palette:
            doc = dict(doc, palette=self._pending_palette)
        tw, th = self.get_canvas_size()
        doc = dict(doc, display=dict(doc.get("display", {}), width=tw, height=th))
        widgets = list(getattr(self, "_locked", [])) + [widget_to_dict(w) for w in self.widgets]
        return Shot(doc, self.theme_dir(), widgets, self._cache)

    def widget_box(self, widget, shot):
        """The pixels a widget covers in the theme, (x1, y1, x2, y2): its own size, or what it paints for a text,
        a clock or an icon."""
        if widget.type in SIZED_TYPES and widget.w and widget.h:
            return widget.x, widget.y, widget.x + widget.w, widget.y + widget.h
        box = shot.extent(widget_to_dict(widget)) if shot else None
        return box or (widget.x, widget.y, widget.x + 16, widget.y + 16)

    def redraw_canvas(self):
        """Redraw the whole theme on the canvas, with the display's own renderer."""
        self.editor_canvas.delete("all")
        self._update_caption()
        tw, th = self.get_canvas_size()
        ox, oy, cw, ch = self.theme_to_canvas_coords(0, 0, tw, th)  # where the screen is, and how big
        scale = cw / tw
        self._boxes = []  # (widget, on-screen box) in drawing order: what a click on the canvas can hit

        shot = None
        try:
            shot = self._shot()
            if shot is not None:
                img = shot.image().resize((max(1, round(cw)), max(1, round(ch))), Image.BILINEAR)
                self._photo = ImageTk.PhotoImage(img)  # kept: Tk drops a picture nobody holds
                self.editor_canvas.create_image(ox, oy, image=self._photo, anchor=tk.NW)
        except Exception as e:  # a theme the renderer refuses: the plain boxes below still let it be edited
            shot = None
            self.app.status_var.set(tr("Preview error: {reason}").format(reason=tr(friendly_error(e))))

        if self.show_grid.get():
            for x in range(0, tw + 1, 20):
                cx = ox + x * scale
                self.editor_canvas.create_line(cx, oy, cx, oy + ch, fill="#3d3d5e", dash=(1, 7))
            for y in range(0, th + 1, 20):
                cy = oy + y * scale
                self.editor_canvas.create_line(ox, cy, ox + cw, cy, fill="#3d3d5e", dash=(1, 7))

        for widget in self.widgets:
            if shot is None:
                self.draw_widget(widget, selected=(widget == self.selected_widget))
                continue
            x1, y1, x2, y2 = self.widget_box(widget, shot)
            box = (ox + x1 * scale, oy + y1 * scale, ox + x2 * scale, oy + y2 * scale)
            self._boxes.append((widget, box))
            if widget == self.selected_widget:
                self.editor_canvas.create_rectangle(box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2,
                                                    outline="#ff2bd6", width=2, dash=(4, 2))
                self.editor_canvas.create_text(box[0], box[1] - 6, text=widget.id, fill="#ff2bd6",
                                               font=("Arial", 8), anchor=tk.SW)
        self.refresh_layers()

    def refresh_layers(self):
        """The list of the theme's widgets, top layer first. It is rebuilt only when a widget was added, removed,
        renamed or selected, not while one is dragged."""
        if not hasattr(self, "_layers"):
            return
        sig = (tuple(id(w) for w in self.widgets), tuple(w.id for w in self.widgets), id(self.selected_widget))
        if sig == self._layers_sig:
            return
        self._layers_sig = sig
        canvas = self._layers._canvas
        keep = canvas.yview()[0]  # the list keeps its scroll position when it is rebuilt
        for child in self._layers.body.winfo_children():
            child.destroy()
        self._layers_title.config(text=f"{tr('IN THIS THEME')} ({len(self.widgets)})")
        bg2, app = PALETTE["bg2"], self.app
        if not self.widgets:
            tk.Label(self._layers.body, text=tr("No widget yet.\nClick a tile above to add one."), bg=bg2,
                     fg=PALETTE["muted"], font=(app.ui_font, 9), justify=tk.LEFT, anchor="w").pack(fill=tk.X)
        for widget in reversed(self.widgets):
            LayerRow(self._layers.body, self._glyphs.get(widget.type, ""), widget.id, tr(widget.type.capitalize()) if widget.type in self._glyphs else widget.type,
                     widget is self.selected_widget, lambda w=widget: self.select_widget(w), bg2, bg2,
                     (ICON_FONT, 11), (app.ui_font, 10), (app.ui_font, 8),
                     movers=(self._mover(widget, 1), self._mover(widget, -1))).pack(fill=tk.X, pady=(0, 6), padx=(0, 6))
        body = self._layers.body
        body.update_idletasks()
        total, view = max(body.winfo_reqheight(), 1), canvas.winfo_height()
        top = keep * total
        if self.selected_widget in self.widgets:  # scroll to the chosen row if it is out of sight
            row_top = list(reversed(self.widgets)).index(self.selected_widget) * (LayerRow.H + 6)
            if row_top < top or row_top + LayerRow.H > top + view:
                top = max(0, row_top - (view - LayerRow.H) / 2)
        canvas.yview_moveto(min(top / total, 1.0))

    def _mover(self, widget, step):
        """A function that moves `widget` one layer up (step 1: drawn later, so on top) or down, or None at the end."""
        i = self.widgets.index(widget) + step
        return (lambda: self.move_widget(widget, step)) if 0 <= i < len(self.widgets) else None

    def move_widget(self, widget, step):
        """Swap `widget` with its neighbour in the drawing order; the list, the canvas and the saved theme follow."""
        i = self.widgets.index(widget)
        j = i + step
        if 0 <= j < len(self.widgets):
            self.widgets[i], self.widgets[j] = self.widgets[j], self.widgets[i]
            self.redraw_canvas()

    def draw_widget(self, widget: WidgetConfig, selected: bool = False):
        """Draw a widget on the canvas."""
        cx, cy, cw, ch = self.theme_to_canvas_coords(widget.x, widget.y, widget.w, widget.h)

        color = tk_colour(self.palette.get(widget.color))
        bg_color = tk_colour(self.palette.get(widget.background)) if widget.background else "#1a1a2e"

        if widget.type == "rect":
            rect = self.editor_canvas.create_rectangle(cx, cy, cx+cw, cy+ch, 
                                                       fill=bg_color, outline=color, width=2)
        elif widget.type == "gauge":
            rect = self.editor_canvas.create_oval(cx, cy, cx+cw, cy+ch, 
                                                  outline=color, width=widget.thickness or 2)
        elif widget.type == "bar":
            rect = self.editor_canvas.create_rectangle(cx, cy, cx+cw, cy+ch, 
                                                       fill=color, outline="")
        elif widget.type == "graph":
            rect = self.editor_canvas.create_rectangle(cx, cy, cx+cw, cy+ch, 
                                                       fill=bg_color, outline=color)
            # Draw sample graph line
            points = []
            for i in range(10):
                px = cx + (cw * i / 9)
                py = cy + ch - (ch * (i % 3 + 1) / 4)
                points.extend([px, py])
            self.editor_canvas.create_line(*points, fill=color, smooth=True, width=2)
        elif widget.type == "text":
            rect = self.editor_canvas.create_text(cx, cy, text=widget.text or widget.id,
                                                   fill=color, font=("Arial", max(6, int(widget.font_size * self.preview_scale))),
                                                   anchor=tk.NW)
        elif widget.type == "clock":
            rect = self.editor_canvas.create_text(cx, cy, text="00:00",
                                                   fill=color, font=("Arial", max(6, int(widget.font_size * self.preview_scale))),
                                                   anchor=tk.NW)
        elif widget.type == "metric":
            rect = self.editor_canvas.create_text(cx, cy, text="100%",
                                                   fill=color, font=("Arial", max(6, int(widget.font_size * self.preview_scale))),
                                                   anchor=tk.NW)
        elif widget.type == "icon":
            rect = self.editor_canvas.create_oval(cx, cy, cx+cw, cy+ch, 
                                                  fill=color, outline="")
        else:
            rect = self.editor_canvas.create_rectangle(cx, cy, cx+cw, cy+ch, 
                                                       fill=bg_color, outline=color)

        # What was drawn, as it is on screen: a clock or a text has no width or height of its own
        box = self.editor_canvas.bbox(rect) or (cx, cy, cx + cw, cy + ch)
        self._boxes.append((widget, box))

        # Selection highlight
        if selected:
            self.editor_canvas.create_rectangle(box[0]-2, box[1]-2, box[2]+2, box[3]+2,
                                               outline="#ff2bd6", width=2, dash=(4, 2))

        # Widget ID label
        self.editor_canvas.create_text(cx, cy-10, text=widget.id, 
                                       fill="#888888", font=("Arial", 7), anchor=tk.S)

    def add_widget(self, wtype: str):
        """Add a new widget to the theme, with values that look right at once on the display."""
        taken = {w.id for w in self.widgets}
        n = len(self.widgets) + 1
        while f"{wtype}_{n}" in taken:
            n += 1
        k = len(self.widgets)
        sized = wtype in SIZED_TYPES
        widget = WidgetConfig(
            id=f"{wtype}_{n}", type=wtype, x=40 + (k % 8) * 16, y=40 + (k % 8) * 16,
            w={"bar": 140, "graph": 140}.get(wtype, 96) if sized else 0,
            h={"bar": 14, "graph": 50}.get(wtype, 96 if wtype == "gauge" else 60) if sized else 0,
            sensor="cpu.load" if wtype in ("gauge", "metric", "graph", "bar") else "",
            format={"clock": "%H:%M", "metric": "{value:.0f}%"}.get(wtype, ""),
            font_size={"clock": 32, "metric": 28, "text": 16}.get(wtype, 12),
            color="@card" if wtype == "rect" and "card" in self.palette.colors else "@accent",
            background="@track" if wtype in ("gauge", "graph", "bar") else "",
            thickness=8 if wtype == "gauge" else 0, text="Label" if wtype == "text" else "", align="left")
        if wtype == "icon":
            widget.extra.update(icon="cpu", size=48, stroke=2)
        elif wtype == "rect":  # a card: rounded, with a thin accent edge
            widget.extra.update(radius=12, outline="@accent", outline_width=1)
        elif wtype == "bar":
            widget.extra.update(radius=7)
        widget.keys = {"x", "y", "color"} | {
            "rect": {"w", "h"}, "gauge": {"w", "h", "sensor", "background", "thickness"},
            "graph": {"w", "h", "sensor", "background"}, "bar": {"w", "h", "sensor", "background"}, "text": {"text", "font_size"},
            "clock": {"format", "font_size"}, "metric": {"sensor", "format", "font_size"}, "icon": set()}[wtype]
        self.widgets.append(widget)
        self.select_widget(widget)

    def select_widget(self, widget: Optional[WidgetConfig]):
        """Select a widget and show its properties."""
        self.selected_widget = widget
        self.redraw_canvas()
        self.update_properties_panel()

    def update_properties_panel(self):
        """Properties of the selected widget, in the app's own controls: muted labels over rounded fields,
        two columns for X/Y and W/H, swatches for the palette and a red Delete button."""
        for child in self.props_inner.winfo_children() + self.props_actions.winfo_children():
            child.destroy()
        if id(self.selected_widget) != self._props_for:  # another widget: start at the top
            self._props_for = id(self.selected_widget)
            self.props_frame._canvas.yview_moveto(0)
        app, host = self.app, self.props_inner
        bg0, bg2 = PALETTE["bg0"], PALETTE["bg2"]
        font, small = (app.ui_font, 10), (app.ui_font, 9)
        mono = ("Cascadia Code", 10)

        if not self.selected_widget:
            tk.Label(host, text=tr("Select a widget on the canvas\nor in the list to edit it."), bg=bg0, fg=PALETTE["muted"],
                     font=font, justify=tk.LEFT, anchor="w").pack(fill=tk.X, pady=(6, 0))
            return
        w = self.selected_widget

        def label(parent, text, top=10):
            tk.Label(parent, text=text, bg=bg0, fg=PALETTE["muted"], font=small, anchor="w").pack(
                fill=tk.X, pady=(top, 4))

        def field(parent, **pack):
            card = RoundedCard(parent, bg2, PALETTE["line2"], bg0, radius=10)
            card.pack(fill=tk.X, **pack)
            return card

        def entry(parent, var, on_change, font_=font, **pack):
            card = field(parent, **pack)
            tk.Entry(card.inner, textvariable=var, bg=bg2, fg=PALETTE["text"], insertbackground=PALETTE["text"],
                     relief=tk.FLAT, highlightthickness=0, font=font_, width=1).pack(fill=tk.X, padx=10, ipady=5)
            card._fit()
            var.trace_add("write", lambda *_: on_change(var.get()))
            return card

        def spin(parent, var, low, high, prop, extra=False, **pack):
            def changed(*_):
                try:
                    value = int(var.get())
                    (self.on_extra_change if extra else self.on_prop_change)(prop, value)
                    if prop in ("x", "y") and getattr(self.selected_widget, prop) != value:
                        var.set(getattr(self.selected_widget, prop))  # it was moved back inside the screen
                except (tk.TclError, ValueError):
                    pass  # ok: half-typed value
            card = field(parent, **pack)
            Stepper(card.inner, var, low, high, bg2, mono).pack(fill=tk.X)
            card._fit()
            var.trace_add("write", changed)

        def pair(first, second):
            """Two labelled fields side by side: (text, var, low, high, prop) each."""
            row = tk.Frame(host, bg=bg0)
            row.pack(fill=tk.X)
            row.columnconfigure(0, weight=1, uniform="pair")
            row.columnconfigure(1, weight=1, uniform="pair")
            for i, (text, var, low, high, prop) in enumerate((first, second)):
                cell = tk.Frame(row, bg=bg0)
                cell.grid(row=0, column=i, sticky="ew", padx=(0, 6) if i == 0 else (6, 0))
                label(cell, text)
                spin(cell, var, low, high, prop, extra=prop in ("size", "stroke"))

        def section(text, first=False):
            if not first:
                tk.Frame(host, bg=PALETTE["line"], height=1).pack(fill=tk.X, pady=(18, 0))
            tk.Label(host, text=text, bg=bg0, fg=PALETTE["muted"], font=(app.ui_font, 8, "bold"),
                     anchor="w").pack(fill=tk.X, pady=(12, 0))

        def hint(text):
            tk.Label(host, text=text, bg=bg0, fg=PALETTE["dim"], font=(app.ui_font, 8), anchor="w", justify=tk.LEFT,
                     wraplength=180).pack(fill=tk.X, pady=(4, 0))

        def colour_field(title, prop):
            """A colour: its real colour as a dot, the value (@name from the palette, or a hex) and Pick, then
            the palette as chips; the chip in use has the accent ring."""
            label(host, title)
            var = tk.StringVar(value=getattr(w, prop))
            row = tk.Frame(host, bg=bg0)
            row.pack(fill=tk.X)
            make_button(row, tr("Pick"), lambda: self.pick_color(var), small, variant="ghost", backdrop=bg0,
                        small=True).pack(side=tk.RIGHT, padx=(8, 0))
            dot = tk.Frame(row, bg=bg0, width=22, height=22, highlightthickness=1, highlightbackground=PALETTE["line2"])
            dot.pack(side=tk.LEFT, padx=(0, 8))
            entry(row, var, lambda v: self.on_prop_change(prop, v), mono, side=tk.LEFT, expand=True)
            chips = {}

            def sync(*_):
                try:
                    dot.config(bg=tk_colour(self.palette.get(var.get())))
                except tk.TclError:
                    pass  # ok: half-typed name
                for name, chip in chips.items():
                    chip.config(highlightbackground=PALETTE["cyan"] if var.get() == f"@{name}" else PALETTE["line2"])
            if self.palette.colors:
                tk.Label(host, text=tr("Theme colours"), bg=bg0, fg=PALETTE["dim"], font=(app.ui_font, 8),
                         anchor="w").pack(fill=tk.X, pady=(8, 4))
                swatches = tk.Frame(host, bg=bg0)
                swatches.pack(fill=tk.X)
                for i, (name, hex_val) in enumerate(list(self.palette.colors.items())[:12]):
                    chip = tk.Frame(swatches, bg=tk_colour(hex_val), width=24, height=24, cursor="hand2",
                                    highlightthickness=2, highlightbackground=PALETTE["line2"])
                    chip.grid(row=i // 6, column=i % 6, padx=(0, 6), pady=(0, 6))
                    chip.bind("<Button-1>", lambda _e, c=f"@{name}": var.set(c))
                    chips[name] = chip
            var.trace_add("write", sync)
            sync()

        head = tk.Frame(host, bg=bg0)
        head.pack(fill=tk.X, pady=(2, 0))
        tk.Label(head, text=self._glyphs.get(w.type, ""), bg=bg0, fg=PALETTE["cyan"], font=(ICON_FONT, 13)).pack(
            side=tk.LEFT, padx=(0, 8))
        tk.Label(head, text=f"{tr('Widget')} {tr(w.type.capitalize())}", bg=bg0, fg=PALETTE["text"],
                 font=(app.ui_semibold, 11)).pack(side=tk.LEFT)

        section(tr("NAME"), first=True)
        label(host, tr("Name"), 6)
        entry(host, tk.StringVar(value=w.id), lambda v: self.on_prop_change("id", v), mono)

        if w.type in ("gauge", "metric", "graph", "bar", "text", "clock"):
            section(tr("CONTENT"))
        if w.type == "text":
            label(host, tr("Text"), 6)
            entry(host, tk.StringVar(value=w.text), lambda v: self.on_prop_change("text", v))
        if w.type in ("gauge", "metric", "graph", "bar"):
            label(host, tr("Sensor (what it shows)"), 6)
            sensor_var = tk.StringVar(value=w.sensor)
            Select(host, ["cpu.load", "cpu.temp", "gpu.load", "gpu.temp", "mem.load", "mem.used", "net.down",
                          "net.up", "disk.load"], w.sensor, lambda v: self.on_prop_change("sensor", v), bg0, font,
                   variable=sensor_var, width=200).pack(anchor="w")
        if w.type in ("metric", "clock"):
            label(host, tr("Format"), 6 if w.type == "clock" else 10)
            entry(host, tk.StringVar(value=w.format), lambda v: self.on_prop_change("format", v), mono)
            hint(tr("%H:%M is 24-hour time, %A %d %B is the date.") if w.type == "clock"
                 else tr("{value:.0f} is the number, 0 decimals."))

        section(tr("POSITION AND SIZE"))
        tw, th = self.get_canvas_size()
        pair(("X (px)", tk.IntVar(value=w.x), 0, tw, "x"), ("Y (px)", tk.IntVar(value=w.y), 0, th, "y"))
        if w.type in SIZED_TYPES:
            pair((tr("Width (px)"), tk.IntVar(value=w.w), 10, 480, "w"), (tr("Height (px)"), tk.IntVar(value=w.h), 10, 480, "h"))
        hint(tr("Pixels from the top left corner of the display. You can also drag the widget on the screen.")
             + (" " + tr("With Align {align}, X is the {edge} of the text.").format(
                 align=tr(w.align.capitalize()), edge=tr({"center": "middle", "right": "right edge"}[w.align]))
                if w.type in ("text", "metric", "clock") and w.align in ("center", "right") else ""))

        section(tr("APPEARANCE"))
        if w.type == "icon":
            self._icon_row(host, w, label, bg0, bg2, font)
            pair((tr("Size (px)"), tk.IntVar(value=int(w.extra.get("size", 32))), 8, 480, "size"),
                 (tr("Stroke"), tk.IntVar(value=int(w.extra.get("stroke", 2))), 1, 6, "stroke"))
        if w.type in ("text", "metric", "clock"):
            label(host, tr("Font size (px)"), 6)
            fs_row = tk.Frame(host, bg=bg0)
            fs_row.pack(fill=tk.X)
            fs_row.columnconfigure(0, weight=1, uniform="pair")
            fs_row.columnconfigure(1, weight=1, uniform="pair")
            fs = tk.Frame(fs_row, bg=bg0)
            fs.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            spin(fs, tk.IntVar(value=w.font_size), 6, 120, "font_size")
        colour_field(tr("Fill") if w.type == "rect" else tr("Color"), "color")
        if w.type in ("gauge", "graph", "bar"):
            colour_field(tr("Background"), "background")
        if w.type in ("rect", "bar"):
            label(host, tr("Corner radius (px)"))
            rr = tk.Frame(host, bg=bg0)
            rr.pack(fill=tk.X)
            rr.columnconfigure(0, weight=1, uniform="pair")
            rr.columnconfigure(1, weight=1, uniform="pair")
            cell = tk.Frame(rr, bg=bg0)
            cell.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            spin(cell, tk.IntVar(value=int(w.extra.get("radius", 0 if w.type == "rect" else 4))), 0, 60, "radius",
                 extra=True)
        if w.type == "gauge":
            label(host, tr("Thickness (px)"))
            pair = tk.Frame(host, bg=bg0)
            pair.pack(fill=tk.X)
            pair.columnconfigure(0, weight=1, uniform="pair")
            pair.columnconfigure(1, weight=1, uniform="pair")
            cell = tk.Frame(pair, bg=bg0)
            cell.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            spin(cell, tk.IntVar(value=w.thickness), 1, 50, "thickness")
        if w.type in ("text", "metric", "clock"):
            label(host, tr("Align"))
            align_var = tk.StringVar(value=w.align)
            Select(host, ["left", "center", "right"], w.align, lambda v: self.on_prop_change("align", v), bg0, font,
                   variable=align_var, width=200).pack(anchor="w")
        tk.Frame(host, bg=bg0, height=8).pack()

        # Duplicate and Delete stay in sight below the scrolling list
        tk.Frame(self.props_actions, bg=PALETTE["line"], height=1).pack(fill=tk.X, pady=(0, 10))
        make_button(self.props_actions, tr("Duplicate widget"), self.duplicate_selected_widget, font, variant="ghost",
                    backdrop=bg0).pack(fill=tk.X, pady=(0, 6))
        make_button(self.props_actions, tr("Delete widget"), self.delete_selected_widget, font, variant="danger",
                    backdrop=bg0).pack(fill=tk.X)

    ICON_GROUPS = (
        ("SHAPES", ("circle", "dot", "square", "block", "triangle", "wedge", "diamond", "hexagon", "star", "plus",
                    "check")),
        ("HARDWARE", ("cpu", "gpu", "ram", "disk", "ssd", "temperature", "fan", "power", "battery", "plug", "usb",
                      "stick", "uptime", "clock")),
        ("NETWORK", ("network", "download", "upload", "ethernet", "wifi", "wifi-1", "wifi-2", "signal", "link",
                     "globe")),
        ("WEATHER", ("sun", "moon", "cloud", "partly", "rain", "snow", "storm", "fog", "humidity", "wind", "sunrise",
                     "sunset", "weather")),
    )

    def _icon_photo(self, name, size, colour):
        """The picture of an icon in a colour (the renderer's own drawing), for the panel and the picker."""
        from libre_panel.icons import draw_icon
        from scripts import shape_icons
        shape_icons.register()
        rgb = tk_colour(colour).lstrip("#")
        rgba = tuple(int(rgb[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
        return ImageTk.PhotoImage(draw_icon(name, size, rgba, 2.0))

    def _icon_row(self, host, w, label, bg0, bg2, font):
        """Appearance of an icon widget: its picture and name, and the button that opens the icon list."""
        label(host, tr("Icon"), 6)
        card = RoundedCard(host, bg2, PALETTE["line2"], bg0, radius=10)
        card.pack(fill=tk.X)
        name = w.extra.get("icon", "cpu")
        try:
            self._icon_thumb = self._icon_photo(name, 28, self.palette.get(w.color))
            tk.Label(card.inner, image=self._icon_thumb, bg=bg2).pack(side=tk.LEFT, padx=(10, 8), pady=6)
        except Exception as e:
            log_swallowed("icon thumbnail in the layers list", e)
        tk.Label(card.inner, text=name, bg=bg2, fg=PALETTE["text"], font=font).pack(side=tk.LEFT)
        make_button(card.inner, "Select icon", self.pick_icon_dialog, (self.app.ui_font, 9), variant="ghost",
                    backdrop=bg2, small=True).pack(side=tk.RIGHT, padx=(0, 8), pady=6)
        card._fit()

    def pick_icon_dialog(self):
        """The icon list in an in-app dialog: every icon and shape as it looks, grouped; a click picks it."""
        w = self.selected_widget
        if not w or w.type != "icon":
            return
        from libre_panel import icons
        from scripts import shape_icons
        shape_icons.register()
        names = list(icons.ICON_NAMES)
        app, bg2 = self.app, PALETTE["bg2"]
        modal = Modal(app, tr("Select icon"), width=540)
        box = tk.Frame(modal.body, bg=bg2, height=400)
        box.pack(fill=tk.X)
        box.pack_propagate(False)
        scroll = ScrollFrame(box, bg2)
        scroll.pack(fill=tk.BOTH, expand=True)
        current, colour = w.extra.get("icon", "cpu"), self.palette.get(w.color)
        photos = []

        def pick(name):
            modal.close()
            if self.selected_widget is w:
                w.extra["icon"] = name
                self.redraw_canvas()
                self.update_properties_panel()

        grouped = {n for _title, group in self.ICON_GROUPS for n in group}
        groups = [(title, [n for n in group if n in names]) for title, group in self.ICON_GROUPS]
        groups.append(("MORE", [n for n in names if n not in grouped]))
        cols = 5
        for title, members in groups:
            if not members:
                continue
            tk.Label(scroll.body, text=title, bg=bg2, fg=PALETTE["muted"], font=(app.ui_font, 8, "bold"),
                     anchor="w").pack(fill=tk.X, pady=(10, 6))
            grid = tk.Frame(scroll.body, bg=bg2)
            grid.pack(anchor="w")
            for i, name in enumerate(members):
                photos.append(self._icon_photo(name, 30, colour))
                IconTile(grid, photos[-1], name, name == current, lambda n=name: pick(n), bg2, bg2,
                         (app.ui_font, 8)).grid(row=i // cols, column=i % cols, padx=(0, 6), pady=(0, 6))
        modal._photos = photos  # Tk drops a picture nobody holds
        modal.show()

    def duplicate_selected_widget(self):
        """A copy of the selected widget, a little to the side, with a free name; it becomes the selection."""
        src = self.selected_widget
        if not src:
            return
        taken = {w.id for w in self.widgets}
        n = len(self.widgets) + 1
        while f"{src.type}_{n}" in taken:
            n += 1
        tw, th = self.get_canvas_size()
        copy = deepcopy(src)
        copy.id = f"{src.type}_{n}"
        copy.x = max(0, min(src.x + 12, tw - max(src.w, 1)))
        copy.y = max(0, min(src.y + 12, th - max(src.h, 1)))
        self.widgets.append(copy)
        self.select_widget(copy)

    def pick_color(self, var: tk.StringVar):
        """In-app colour picker: swatches (the app's and common ones) and a hex box."""
        modal = Modal(self.app, tr("Pick a colour"), width=360)
        bg2 = PALETTE["bg2"]
        chosen = tk.StringVar(value=self.palette.get(var.get()) if var.get() else "#00E5FF")
        swatches = [PALETTE[k] for k in ("cyan", "blue", "violet", "green", "warn", "crit", "text", "muted", "bg3")] + [
            "#FF2BD6", "#FF7A00", "#FFD400", "#00FF9C", "#FFFFFF", "#000000", "#2A2A35"]
        grid = tk.Frame(modal.body, bg=bg2)
        grid.pack(anchor="w")
        for i, colour in enumerate(swatches):
            cell = tk.Frame(grid, bg=PALETTE["line2"], padx=1, pady=1, cursor="hand2")
            cell.grid(row=i // 8, column=i % 8, padx=3, pady=3)
            tk.Frame(cell, bg=colour, width=28, height=28).pack()
            for part in (cell, *cell.winfo_children()):
                part.bind("<Button-1>", lambda _e, c=colour: chosen.set(c.upper()))
        form_label(modal.body, tr("Hex colour"), (self.app.ui_font, 9))
        form_entry(modal.body, chosen, ("Cascadia Code", 10))

        def apply():
            value = chosen.get().strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                self.app.toast(tr("Use a colour like #00E5FF"), "error")
                return
            modal.close()
            var.set(value)
            self.on_prop_change("color", value)
        actions = tk.Frame(modal.body, bg=bg2)
        actions.pack(fill=tk.X, pady=(18, 0))
        make_button(actions, tr("Use colour"), apply, (self.app.ui_font, 10), variant="primary", backdrop=bg2).pack(
            side=tk.RIGHT)
        make_button(actions, tr("Cancel"), modal.close, (self.app.ui_font, 10), variant="ghost", backdrop=bg2).pack(
            side=tk.RIGHT, padx=(0, 8))
        modal.show()

    def on_prop_change(self, prop: str, value):
        """Handle property change."""
        if self.selected_widget:
            setattr(self.selected_widget, prop, value)
            self.selected_widget.keys.add(prop)
            if prop in ("x", "y"):
                self.keep_inside(self.selected_widget)
            self.redraw_canvas()

    def keep_inside(self, widget):
        """Move the widget back so everything it paints stays on the screen (not only its corner)."""
        tw, th = self.get_canvas_size()
        try:
            box = self.widget_box(widget, self._shot())
        except Exception:
            box = (widget.x, widget.y, widget.x + max(widget.w, 1), widget.y + max(widget.h, 1))
        widget.x = max(0, min(widget.x, tw - (box[2] - widget.x)))
        widget.y = max(0, min(widget.y, th - (box[3] - widget.y)))

    def on_extra_change(self, key, value):
        """A property that has no field of its own in WidgetConfig (icon, size, stroke): kept in `extra`."""
        if self.selected_widget:
            self.selected_widget.extra[key] = value
            self.redraw_canvas()

    def delete_selected_widget(self):
        """Delete the selected widget."""
        if self.selected_widget:
            self.widgets.remove(self.selected_widget)
            self.selected_widget = None
            self.redraw_canvas()
            self.update_properties_panel()

    def on_canvas_click(self, event):
        """Handle canvas click - select widget."""
        theme_x, theme_y = self.canvas_to_theme_coords(event.x, event.y)

        widget = pick_topmost(self._boxes, event.x, event.y)  # the topmost one under the pointer
        if widget is not None:
            self.select_widget(widget)
            self.drag_data["x"] = theme_x - widget.x  # drag offset
            self.drag_data["y"] = theme_y - widget.y
            self.drag_data["widget"] = widget
            return

        # Clicked on empty space - deselect
        self.select_widget(None)

    def on_canvas_drag(self, event):
        """Handle canvas drag - move widget."""
        if self.drag_data["widget"]:
            theme_x, theme_y = self.canvas_to_theme_coords(event.x, event.y)
            widget = self.drag_data["widget"]
            widget.x = int(theme_x - self.drag_data["x"])
            widget.y = int(theme_y - self.drag_data["y"])
            self.keep_inside(widget)
            self.redraw_canvas()
            self.update_properties_panel()

    def on_canvas_release(self, event):
        """Handle canvas drag release."""
        self.drag_data = {"x": 0, "y": 0, "widget": None}

    def on_canvas_double_click(self, event):
        """Handle double click - could open advanced properties."""
        pass

    def load_current_theme(self):
        """Load the current theme's widgets (the folder of the orientation shown)."""
        theme_path = self.theme_dir() / "theme.json"
        self._shown = self.current_orientation()
        self._stash.pop((self.theme_name, self._shown), None)
        self._pending_palette = None
        if self._named != self.theme_name:  # a theme was loaded: show its name
            self._named = self.theme_name
            # a built-in theme cannot be saved over: the name box offers a copy's name instead
            self.name_var.set(self.theme_name if is_editable_theme(self.theme_name)
                              else self._suggest_name(f"{self.theme_name}-copy"))
        if theme_path.exists():
            with open(theme_path, encoding="utf-8") as f:
                data = json.load(f)
            # locked background widgets are skipped here and put back under the widgets when the theme is drawn
            self._locked = [w for w in data.get("widgets", []) if w.get("locked")]
            self._doc = {k: v for k, v in data.items() if k != "widgets"}
            self._cache = {}
            self.widgets = [widget_from_dict(w) for w in data.get("widgets", []) if not w.get("locked")]
            self.palette = self.load_palette()
            self.redraw_canvas()

    def _theme_taken(self, slug) -> bool:
        themes = DATA_ROOT / "themes"
        return any(theme_paths.folder(themes, n).exists() for n in (slug, f"{slug}-320x480"))

    def _suggest_name(self, base) -> str:
        return unique_theme_name(self._theme_taken, base)

    def start_draft(self):
        """New theme: the blank canvas opened with a suggested name (custom-<date>). Nothing is written to
        disk and the applied theme does not change until the user clicks Save theme."""
        base = "custom-blank-canvas"
        if not theme_paths.folder(DATA_ROOT / "themes", base).is_dir():
            self.app.toast(tr("The blank canvas theme is missing."), "error")
            return
        self.theme_name, self._named = base, None
        self.load_current_theme()
        self.name_var.set(self._suggest_name(f"custom-{datetime.now():%Y-%m-%d}"))
        self._draft = True  # a draft has no name of its own yet: every existing theme name is taken, its base too
        self.app.toast(tr("New theme: nothing is saved until you click Save theme."))

    def save_theme(self):
        """Save into the custom themes folder: <name> (landscape) or <name>-320x480 (portrait), the name from the name box."""
        orientation = self.current_orientation()
        slug = self.name_slug()
        themes = theme_paths.custom_dir()
        folders = {"landscape": themes / slug, "portrait": themes / f"{slug}-320x480"}
        sources = {o: self.theme_dir(o) for o in folders}
        if (slug != self.theme_name or getattr(self, "_draft", False)) and self._theme_taken(slug):
            self.app.toast(tr("A theme named \"{slug}\" already exists. Pick another name.").format(slug=slug), "error")
            return
        if not is_editable_theme(slug):
            self.app.toast(tr("Built-in themes cannot be changed. Give it another name to save a copy."), "error")
            return
        try:
            themes.mkdir(parents=True, exist_ok=True)
            for o, dst in folders.items():  # a new name gets both orientations, copied from the loaded theme
                if not (dst / "theme.json").is_file() and (sources[o] / "theme.json").exists():
                    shutil.rmtree(dst, ignore_errors=True)  # a half-made folder from an earlier failed copy
                    shutil.copytree(sources[o], dst)
            theme_path = folders[orientation] / "theme.json"
            if not theme_path.exists():
                self.app.toast(tr("Theme file not found: {path}").format(path=theme_path), "error")
                return
            with open(theme_path, encoding="utf-8") as f:
                data = json.load(f)
            # Update widgets (preserve locked ones)
            locked_widgets = [w for w in data.get("widgets", []) if w.get("locked")]
            data["widgets"] = locked_widgets + [widget_to_dict(w) for w in self.widgets]
            if self._pending_palette:
                data["palette"] = self._pending_palette
            if slug != self.theme_name:
                data["name"] = slug
            shutil.copy2(theme_path, theme_path.with_suffix(".json.bak"))
            with open(theme_path, "w") as f:
                json.dump(data, f, indent=2)
            if slug != "custom-blank-canvas":  # the card reads the landscape file, whichever orientation was saved
                for other in folders.values():
                    theme_paths.set_title(other, slug)
        except (OSError, ValueError) as e:
            self.app.toast(tr("Could not save {slug}: {reason}").format(slug=slug, reason=tr(friendly_error(e))), "error")
            return
        self._stash = {(slug if k[0] == self.theme_name else k[0], k[1]): v for k, v in self._stash.items()}
        self.theme_name = self._named = slug
        self._pending_palette = None
        self.name_var.set(slug)
        self.app.toast(tr("Theme saved: {slug} ({orientation})").format(slug=slug, orientation=orientation))
        self.app.status_var.set(tr("Theme saved: {slug} ({orientation})").format(slug=slug, orientation=orientation))
        if hasattr(self.app, "_gallery_grid"):
            self.app._gallery_render()

    def name_slug(self) -> str:
        """Folder name from the name box: lower case, letters, digits and dashes; empty gives a default."""
        return self._slug(self.name_var.get())

    @staticmethod
    def _slug(text) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()).strip("-")
        return slug.removesuffix("-320x480").strip("-") or "custom-theme"

    def load_theme_dialog(self):
        """Pick a theme to edit, in an in-app dialog: a click on a theme loads it."""
        app = self.app
        modal = Modal(app, tr("Load theme"), width=380)
        bg2 = PALETTE["bg2"]
        tk.Label(modal.body, text=tr("Your themes and the Custom Blank Canvas."), bg=bg2, fg=PALETTE["muted"],
                 font=(app.ui_font, 9), anchor="w").pack(fill=tk.X, pady=(0, 8))
        box = tk.Frame(modal.body, bg=bg2, height=300)
        box.pack(fill=tk.X)
        box.pack_propagate(False)
        scroll = ScrollFrame(box, bg2)
        scroll.pack(fill=tk.BOTH, expand=True)

        def load(name):
            self.theme_name = name
            self.settings.theme = name
            self.settings.save()
            self.load_current_theme()
            app.theme_var.set(name)
            app.on_theme_change()
            modal.close()

        for name in filter(is_editable_theme, self.app.get_available_themes()):  # built-in themes are not edited
            ChoiceTile(scroll.body, name, name == self.theme_name, lambda n=name: load(n), bg2,
                       (app.ui_semibold, 10)).pack(fill=tk.X, pady=(0, 6), padx=(0, 4))
        modal.show()

    def export_json(self):
        """Export theme as JSON file."""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"{self.theme_name}_custom.json"
        )
        if filepath:
            theme_path = self.theme_dir() / "theme.json"
            with open(theme_path, encoding="utf-8") as f:
                data = json.load(f)
            data["widgets"] = [w for w in data.get("widgets", []) if w.get("locked")] + [widget_to_dict(w) for w in self.widgets]
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            self.app.toast(tr("Theme exported to {path}").format(path=filepath))

    def import_json(self):
        """Import a theme .json (an exported file or a theme.json): its widgets and palette are loaded into the
        editor under a suggested name. Nothing is saved until the user clicks Save theme."""
        filepath = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not filepath:
            return
        path = Path(filepath)
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or not isinstance(data.get("widgets"), list):
                raise ValueError("it has no widget list")
            widgets = [widget_from_dict(w) for w in data["widgets"] if isinstance(w, dict) and not w.get("locked")]
        except (OSError, ValueError, TypeError) as e:  # a bad file leaves the current layout untouched
            self.app.toast(tr("Could not import {name}: {reason}").format(name=path.name, reason=tr(friendly_error(e))), "error")
            return
        self.widgets = widgets
        if isinstance(data.get("palette"), dict):
            self._pending_palette = data["palette"]
            self.palette = ThemePalette(data["palette"])
        self.name_var.set(self._suggest_name(self._slug(str(data.get("name") or path.stem))))
        self.redraw_canvas()
        self.app.toast(tr("Imported {count} widgets from {name}. Click Save theme to keep them.").format(count=len(widgets), name=path.name))


DEFAULT_THEME = "cyberpunk-neon"  # applied when the applied custom theme is deleted
