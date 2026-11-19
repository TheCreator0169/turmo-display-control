"""Gallery page and the in-app dialogs and toast (v0.2.3): methods of TurmoApp, mixed in."""

from scripts.gui_common import *  # noqa: F401,F403
from scripts.theme_editor import DEFAULT_THEME  # noqa: E402


class _SearchQuery:
    """The text of a search box that shows a hint while it is empty. `get()` is "" while the hint shows."""

    def __init__(self, entry, hint, fg, hint_fg):
        self._entry, self._hint, self._fg, self._hint_fg, self._showing = entry, hint, fg, hint_fg, False
        entry.bind("<FocusIn>", lambda e: self._focus(True))
        entry.bind("<FocusOut>", lambda e: self._focus(False))
        self._focus(False)

    def _focus(self, focused):
        if focused and self._showing:
            self._entry.delete(0, tk.END)
            self._entry.config(fg=self._fg)
            self._showing = False
        elif not focused and not self._entry.get():
            self._entry.insert(0, self._hint)
            self._entry.config(fg=self._hint_fg)
            self._showing = True

    def get(self):
        return "" if self._showing else self._entry.get()


# ─── Main Application ───


class GalleryPage:
    """Methods of TurmoApp (mixed in), moved out of turmo_app_enhanced.py in v0.2.3."""

    def build_gallery_tab(self, nb):
        """Gallery (v0.2.0 design): header with Import and New theme, a toolbar with the category pills and
        the search box, then the theme cards."""
        bg0, bg2 = PALETTE["bg0"], PALETTE["bg2"]
        frame = tk.Frame(nb, bg=bg0)
        nb.add(frame, text="Gallery")
        head = page_header(frame, tr("Theme gallery"), tr("Pick or customise the look of the 3.5\u2033 display."), bg0,
                           (self.ui_semibold, 16), (self.ui_font, 10))
        head.pack(fill=tk.X, padx=24, pady=(24, 0))
        make_button(head.actions, tr("Import theme (.json)"), self.gallery_import, (self.ui_font, 10),
                    variant="ghost", backdrop=bg0).pack(side=tk.LEFT, padx=(0, 8))
        make_button(head.actions, tr("New theme"), self.gallery_new, (self.ui_font, 10),
                    variant="primary", backdrop=bg0).pack(side=tk.LEFT)
        # Landscape / Portrait switch, centred in the header: the same setting as the Dashboard and Monitor
        centre = tk.Frame(head, bg=bg0)
        centre.place(relx=0.5, rely=0.5, anchor="center", x=36)
        labels = {}
        for name in ("Landscape", "Portrait"):
            labels[name] = tk.Label(centre, text=tr(name), bg=bg0, font=(self.ui_semibold, 10))
        self.gallery_portrait = tk.BooleanVar(value=not self.landscape_var.get())

        def tint(*_):
            portrait = self.gallery_portrait.get()
            labels["Landscape"].config(fg=PALETTE["muted"] if portrait else PALETTE["text"])
            labels["Portrait"].config(fg=PALETTE["text"] if portrait else PALETTE["muted"])

        def chosen(portrait):
            self.landscape_var.set(not portrait)
            self.on_orientation_change()
        labels["Landscape"].pack(side=tk.LEFT, padx=(0, 10))
        Switch(centre, self.gallery_portrait.get(), chosen, bg0, variable=self.gallery_portrait).pack(side=tk.LEFT)
        labels["Portrait"].pack(side=tk.LEFT, padx=(10, 0))
        self.gallery_portrait.trace_add("write", tint)
        self.landscape_var.trace_add("write", lambda *_: self.gallery_portrait.set(not self.landscape_var.get()))
        tint()

        def align_switch(_e=None):  # same x as before; the centre line is the buttons', not the header's
            head.update_idletasks()
            act = head.actions
            centre.place_configure(rely=0, y=act.winfo_y() + act.winfo_height() / 2, anchor="center")
        head.actions.bind("<Configure>", align_switch)
        bar = tk.Frame(frame, bg=bg0)
        # the pills end where the theme tiles end: the grid stops short of its scroll bar (10 px + 6 px gap)
        bar.pack(fill=tk.X, padx=(24, 24 + 16), pady=(16, 12))
        # search box: a rounded field with a magnifier and a hint
        box = RoundedCard(bar, bg2, PALETTE["line2"], bg0, radius=10, width=280)
        box.pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(box.inner, text="\uE721", bg=bg2, fg=PALETTE["muted"], font=(ICON_FONT, 10)).pack(
            side=tk.LEFT, padx=(10, 6))
        entry = tk.Entry(box.inner, bg=bg2, fg=PALETTE["text"], insertbackground=PALETTE["text"], relief=tk.FLAT,
                         highlightthickness=0, font=(self.ui_font, 10), width=1)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 10))
        self._gallery_query = _SearchQuery(entry, tr("Search themes\u2026"), PALETTE["text"], PALETTE["dim"])
        entry.bind("<KeyRelease>", lambda e: self._gallery_render())
        self._gallery_category = "All"
        self._gallery_cat_buttons = {}
        for cat in GALLERY_CATEGORIES:
            btn = RoundedButton(bar, tr(cat), lambda c=cat: self._gallery_set_category(c), bg0, bg2,
                                PALETTE["muted"], PALETTE["bg3"], (self.ui_font, 10), radius=None,
                                padx=12, pady=6)
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 0 if cat == GALLERY_CATEGORIES[-1] else 8))
            self._gallery_cat_buttons[cat] = btn
        holder = tk.Frame(frame, bg=bg0)
        holder.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 24))
        canvas = tk.Canvas(holder, bg=bg0, highlightthickness=0)
        scroll = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._gallery_canvas = canvas
        self._gallery_grid = tk.Frame(canvas, bg=bg0)
        window = canvas.create_window((0, 0), window=self._gallery_grid, anchor="nw")
        self._gallery_grid.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        # one permanent binding that checks the pointer: a bind_all / unbind_all pair on Enter / Leave would
        # remove the Dashboard's wheel binding as well
        def gallery_wheel(ev):
            under = canvas.winfo_containing(ev.x_root, ev.y_root)
            if under is not None and str(under).startswith(str(canvas)):
                canvas.yview_scroll(int(-ev.delta / 120), "units")
        canvas.bind_all("<MouseWheel>", gallery_wheel, add="+")
        self._gallery_images = []
        self._gallery_set_category("All")

    def _gallery_set_category(self, category):
        self._gallery_category = category
        for cat, btn in self._gallery_cat_buttons.items():
            active = cat == category
            # the chosen pill is solid cyan with dark text; it keeps its colour under the pointer
            btn.config(bg=PALETTE["cyan"] if active else PALETTE["bg2"],
                       fg=PALETTE["on_accent"] if active else PALETTE["muted"],
                       active_bg=PALETTE["cyan"] if active else PALETTE["bg3"])
        self._gallery_render()

    def _gallery_render(self):
        top = self._gallery_canvas.yview()[0]  # keep the scroll position: the page is rebuilt on Apply
        for child in self._gallery_grid.winfo_children():
            child.destroy()
        self._gallery_images = []
        names = [t for t in self.get_available_themes() if t != "minimal"]
        order = self.settings.theme_order
        declared = {}
        for slug in names:  # a custom theme may name its category in theme.json
            if is_custom_theme(slug):
                try:
                    declared[slug] = json.loads((theme_paths.folder(DATA_ROOT / "themes", slug) / "theme.json")
                                                .read_text(encoding="utf-8")).get("category")
                except Exception as _e:
                    log_swallowed("theme category read", _e)
        shown = filter_themes(names, self._gallery_category, self._gallery_query.get(), order, declared)
        self._gallery_names, self._gallery_shown = names, shown  # the organize menu moves cards inside these
        for c in range(4):
            self._gallery_grid.columnconfigure(c, weight=1, uniform="gallery")
        for i, slug in enumerate(shown):
            card = self._gallery_card(self._gallery_grid, slug)
            card.grid(row=i // 4, column=i % 4, sticky="nsew", padx=6, pady=6)
        # without this the old scroll position outlives the old, taller content and the page shows nothing
        self._gallery_grid.update_idletasks()
        self._gallery_canvas.configure(scrollregion=self._gallery_canvas.bbox("all"))
        self._gallery_canvas.yview_moveto(top)
        self._gallery_pictures(shown)

    def _gallery_pictures(self, shown):
        """v0.3.0: the user's own themes get their picture drawn when they have none (or an old one); the cards are
        redrawn once it is there. The official themes ship theirs."""
        from scripts.theme_picture import PictureMaker
        maker = getattr(self, "_picture_maker", None)
        if maker is None:
            maker = self._picture_maker = PictureMaker(log_swallowed)
        folders = [theme_paths.custom_dir() / f"{slug}{variant}" for slug in shown if theme_paths.is_custom(slug)
                   for variant in ("", "-320x480")]
        if not maker.start(folders):
            return

        def done():
            if not self.root.winfo_exists():
                return
            if maker.running():
                self.root.after(300, done)
            elif maker.poll() and hasattr(self, "_gallery_grid"):
                self._gallery_render()  # nothing is stale now (or it failed once): no loop
        self.root.after(300, done)

    def _gallery_card(self, parent, slug):
        import json
        bg2 = PALETTE["bg2"]
        try:
            meta = json.loads((theme_paths.folder(DATA_ROOT / "themes", slug) / "theme.json").read_text(encoding="utf-8"))
        except Exception as _e:
            log_swallowed("theme meta read", _e)
            meta = {}
        pal = meta.get("palette", {})
        applied = slug == self.settings.theme
        outer = RoundedCard(parent, bg2, PALETTE["cyan"] if applied else PALETTE["line"], PALETTE["bg0"],
                            border_w=2)
        card = outer.inner
        from scripts.card_marks import BAR, ICON, MARGIN, corner_icons
        portrait = self.settings.orientation == "portrait"
        # landscape: a bar above keeps the icons off the picture. Portrait: the picture is narrow, the corners are free, so
        # the icons float in them and the picture takes the height the bar would use
        thumb = self._gallery_thumb(slug, size=(190, 126) if portrait else (190, 118 + 4 - BAR))
        marks = [("ne", "organize", lambda s=slug: self._gallery_organize_menu(card, s))]  # every card
        if is_custom_theme(slug):  # the user's own themes: the bin at the top left (pencil and copy are at the bottom)
            marks.insert(0, ("nw", "delete", lambda s=slug: self.gallery_delete(s)))
        top = 8 if portrait else 0
        if not portrait:
            tk.Frame(card, bg=bg2, height=BAR + 2).pack(fill=tk.X)
        if thumb is not None:
            tk.Label(card, image=thumb, bg=bg2, bd=0).pack(padx=10, pady=(top, 6))
        else:
            tk.Label(card, text=tr("No preview"), bg=bg2, fg=PALETTE["muted"]).pack(padx=10, pady=(top, 6), ipady=36)
        corner_icons(card, bg2, marks)  # created last, so they sit in front of the picture
        if applied:  # ACTIVE badge, top left of the card (the organize chip has the right corner)
            badge = Badge(card, bg2, (self.ui_font, 8, "bold"), solid=True)
            badge.set(tr("ACTIVE"), PALETTE["cyan"])
            badge.place(relx=0.0, x=2 + MARGIN + ICON + 12 if is_custom_theme(slug) else 14, y=2 + MARGIN + 3, anchor="nw")  # right of the bin
        strip = tk.Frame(card, bg=bg2)
        strip.pack(fill=tk.X, padx=12, pady=(4, 8))
        for colour in (pal.get("accent", PALETTE["cyan"]), pal.get("bg", PALETTE["bg0"]),
                       mix(PALETTE["text"], bg2, 0.3)):
            tk.Frame(strip, bg=colour, height=8).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        tk.Label(card, text=meta.get("name", slug), bg=bg2, fg=PALETTE["text"], anchor="w",
                 font=(self.ui_semibold, 11)).pack(fill=tk.X, padx=12)
        self._gallery_desc(card, bg2, slug, meta.get("description", "") if is_custom_theme(slug) else tr(meta.get("description", "")))
        row = tk.Frame(card, bg=bg2)
        row.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(10, 12))  # bottom: Apply lines up across a row of cards
        for col in (0, 2):  # equal side columns keep Apply in the middle
            row.columnconfigure(col, weight=1, uniform="side")
        make_button(row, tr("Active") if applied else tr("Apply"), lambda s=slug: self.gallery_apply(s),
                    (self.ui_font, 10), variant="primary" if applied else "ghost", backdrop=bg2,
                    small=True).grid(row=0, column=1)
        icon = (ICON_FONT, 11)
        if is_editable_theme(slug):  # edit at the left margin; the user's own themes (never the official ones)
            make_button(row, "", lambda s=slug: self.gallery_edit(s), icon, variant="ghost", backdrop=bg2,
                        small=True, padx=9).grid(row=0, column=0, sticky="w")
        if is_editable_theme(slug) or is_custom_theme(slug):  # copy (and delete) at the right margin
            right = tk.Frame(row, bg=bg2)
            right.grid(row=0, column=2, sticky="e")
            make_button(right, "", lambda s=slug: self.gallery_duplicate(s), icon, variant="ghost",
                        backdrop=bg2, small=True, padx=9).pack(side=tk.LEFT)
        return outer

    def _gallery_desc(self, parent, bg2, slug, text):
        """The theme's description cut to two lines with 'See more'; a click shows all of it followed by
        'Show less'. The open cards are remembered, so the page rebuilt on Apply keeps them open."""
        import tkinter.font as tkfont
        font = tkfont.Font(root=self.root, font=(self.ui_font, 9))
        width, line_h, more, less = 162, font.metrics("linespace"), tr("See more"), tr("Show less")
        short, lines = collapse_description(text, font.measure, width, more)
        opened = self.__dict__.setdefault("_gallery_open", set())
        box = tk.Frame(parent, bg=bg2, width=width + 12)
        box.pack_propagate(False)
        box.pack(anchor="w", padx=(15, 8), pady=(2, 0))
        t = tk.Text(box, bg=bg2, fg=PALETTE["muted"], font=font, relief=tk.FLAT, bd=0, highlightthickness=0,
                    padx=0, pady=0, wrap="word", cursor="arrow", exportselection=False, takefocus=0)
        t.pack(fill=tk.BOTH, expand=True)
        t.tag_configure("link", foreground=PALETTE["cyan"])
        t.tag_bind("link", "<Enter>", lambda _e: t.config(cursor="hand2"))
        t.tag_bind("link", "<Leave>", lambda _e: t.config(cursor="arrow"))
        t.bind("<Button-1>", lambda _e: "break")  # no caret, no selection

        def render(expanded):
            """Put the text in the box (cut or whole) and return how many lines it takes."""
            t.config(state=tk.NORMAL)
            t.delete("1.0", tk.END)
            if short is None:
                t.insert(tk.END, "\n".join(lines))
                n = len(lines)
            elif expanded:
                fits = font.measure(lines[-1] + "   " + less) <= width
                t.insert(tk.END, "\n".join(lines) + ("   " if fits else "\n"))
                t.insert(tk.END, less, "link")
                n = len(lines) + (0 if fits else 1)
            else:
                t.insert(tk.END, "\n".join(short) + " ")
                t.insert(tk.END, more, "link")
                n = len(short)
            t.config(state=tk.DISABLED)
            return n

        def relayout():
            parent.master._fit()  # the card (parent is its inner frame) asks for its new height
            self._gallery_grid.update_idletasks()
            self._gallery_canvas.configure(scrollregion=self._gallery_canvas.bbox("all"))

        state = {"anim": None, "leave": None}

        def animate(expanded):
            """Cut or whole text in one layout pass (a taller card moves every row below it, which costs about
            100 ms per pass: sliding the height in steps made the page lag), then the text fades in from the
            card colour, which needs no layout."""
            if state["anim"]:
                box.after_cancel(state["anim"])
            box.config(height=(render(True) if expanded else render(False)) * line_h)
            relayout()

            def fade(k):
                state["anim"] = None
                if not box.winfo_exists():
                    return
                t.config(fg=mix(PALETTE["muted"], bg2, k / 4))
                t.tag_configure("link", foreground=mix(PALETTE["cyan"], bg2, k / 4))
                if k < 4:
                    state["anim"] = box.after(30, fade, k + 1)
            fade(1)

        def toggle(_e):
            opened.symmetric_difference_update({slug})
            animate(slug in opened)
            return "break"

        def pointer_outside():
            card = parent.master
            x, y = card.winfo_pointerxy()
            inside_x = card.winfo_rootx() <= x < card.winfo_rootx() + card.winfo_width()
            inside_y = card.winfo_rooty() <= y < card.winfo_rooty() + card.winfo_height()
            return not (inside_x and inside_y)

        def close_if_left():
            state["leave"] = None
            if slug in opened and parent.master.winfo_exists() and pointer_outside():
                opened.discard(slug)
                animate(False)

        def pointer_left(_e):  # an open description closes by itself, after a short pause, once the pointer is out
            if slug in opened and state["leave"] is None and pointer_outside():
                state["leave"] = box.after(150, close_if_left)
        t.tag_bind("link", "<Button-1>", toggle)
        parent.master.bind("<Leave>", pointer_left, add="+")
        box.config(height=render(slug in opened) * line_h)

    def _gallery_organize_menu(self, card, slug):
        """A small menu under the organize chip: move the theme inside the cards on screen. It is placed over
        the card, so the card keeps its size; a second click on the chip, a choice or leaving it closes it."""
        old = getattr(self, "_gallery_menu", None)
        self._gallery_menu = None
        if old is not None and old.winfo_exists():
            same = old.master is card
            old.destroy()
            if same:
                return
        full = order_themes(self._gallery_names, self.settings.theme_order)
        shown = self._gallery_shown
        bg1 = PALETTE["bg1"]
        menu = RoundedCard(card, bg1, PALETTE["line2"], PALETTE["bg2"], radius=10)
        menu.place(relx=1.0, x=-10, y=44, anchor="ne")
        self._gallery_menu = menu
        labels = (("start", "Move to start"), ("left", "Move left"), ("right", "Move right"), ("end", "Move to end"))
        tk.Frame(menu.inner, bg=bg1, height=4).pack()
        for action, text in labels:
            possible = move_theme(full, shown, slug, action) != full
            row = tk.Label(menu.inner, text=text, bg=bg1, anchor="w", padx=14, pady=5, font=(self.ui_font, 10),
                           fg=PALETTE["text"] if possible else PALETTE["dim"],
                           cursor="hand2" if possible else "arrow")
            row.pack(fill=tk.X)
            if possible:
                row.bind("<Enter>", lambda _e, r=row: r.config(bg=PALETTE["bg3"]))
                row.bind("<Leave>", lambda _e, r=row: r.config(bg=bg1))
                row.bind("<Button-1>", lambda _e, a=action: self._gallery_move(slug, a))
        tk.Frame(menu.inner, bg=bg1, height=4).pack()
        menu._fit()

        def left_menu(_e):
            def check():
                if not menu.winfo_exists():
                    return
                x, y = menu.winfo_pointerxy()
                inside = (menu.winfo_rootx() <= x < menu.winfo_rootx() + menu.winfo_width()
                          and menu.winfo_rooty() <= y < menu.winfo_rooty() + menu.winfo_height())
                if not inside:
                    menu.destroy()
            menu.after(250, check)
        menu.bind("<Leave>", left_menu)

    def _gallery_move(self, slug, action):
        full = order_themes(self._gallery_names, self.settings.theme_order)
        self.settings.theme_order = move_theme(full, self._gallery_shown, slug, action)
        self.settings.save()
        self._gallery_render()

    def gallery_delete(self, slug):
        """Delete a custom theme (its folder and its portrait variant) after a confirmation. The official
        themes are refused. If the theme is the applied one, the default theme is applied instead."""
        if not is_custom_theme(slug):
            self.toast("Official themes cannot be deleted.")
            return
        applied = slug == self.settings.theme
        themes = theme_paths.custom_dir().resolve()  # only the user's themes are deletable
        folders = [themes / f"{slug}{v}" for v in ("", "-320x480")]
        folders = [f for f in folders if f.is_dir() and f.resolve().parent == themes]
        if not folders:
            self.toast(f"The theme \"{slug}\" is not in the custom themes folder, so it cannot be deleted here.")
            return
        note = f"\n\nIt is the applied theme: {DEFAULT_THEME} will be applied instead." if applied else ""
        self.confirm(tr("Delete theme"), f"Delete the theme \"{slug}\"?{note}\n\nIts folder is removed from disk. "
                     "This cannot be undone.", tr("Delete"), lambda: self._delete_theme_folders(slug, folders, applied),
                     danger=True)

    def confirm(self, title, text, yes_label, on_yes, danger=False, no_label=None, on_no=None):
        """Ask in an in-app dialog (never a Windows message box); `on_yes()` runs when the user agrees."""
        modal = Modal(self, title, width=400)
        bg2 = PALETTE["bg2"]
        tk.Label(modal.body, text=text, bg=bg2, fg=PALETTE["text"], font=(self.ui_font, 10), justify=tk.LEFT,
                 anchor="w", wraplength=350).pack(fill=tk.X, pady=(4, 0))
        actions = tk.Frame(modal.body, bg=bg2)
        actions.pack(fill=tk.X, pady=(20, 0))

        def yes():
            modal.close()
            on_yes()
        make_button(actions, yes_label, yes, (self.ui_font, 10), variant="danger" if danger else "primary",
                    backdrop=bg2).pack(side=tk.RIGHT)
        def no():
            modal.close()
            if on_no:
                on_no()
        make_button(actions, no_label or tr("Cancel"), no, (self.ui_font, 10), variant="ghost", backdrop=bg2).pack(
            side=tk.RIGHT, padx=(0, 8))
        modal.show()

    def show_info(self, title, text, modal=False):
        """A short notice: a toast, or an in-app dialog when `modal` (long text)."""
        if modal:
            self.alert(title, text)
        else:
            self.toast(text)

    def show_warning(self, title, text):
        self.alert(title, text)

    def show_error(self, title, text):
        self.alert(title, text, kind="error")

    def alert(self, title, text, kind="info"):
        """An in-app dialog with one OK button (never a Windows message box)."""
        modal = Modal(self, title, width=440)
        bg2 = PALETTE["bg2"]
        tk.Label(modal.body, text=text, bg=bg2, fg=PALETTE["crit"] if kind == "error" else PALETTE["text"],
                 font=(self.ui_font, 10), justify=tk.LEFT, anchor="w", wraplength=390).pack(fill=tk.X, pady=(4, 0))
        make_button(modal.body, tr("OK"), modal.close, (self.ui_font, 10), variant="primary", backdrop=bg2).pack(
            anchor="e", pady=(20, 0))
        modal.show()

    def _delete_theme_folders(self, slug, folders, applied):
        import shutil
        try:
            if applied:  # leave the theme before its folder goes
                self.theme_var.set(DEFAULT_THEME)
                self.on_theme_change()
            for folder in folders:
                shutil.rmtree(folder)
        except OSError as e:
            self.toast(f"Could not delete {slug}: {e}", "error")
        else:
            self.status_var.set(f"Deleted theme {slug}")
        self._refresh_dashboard_status()
        self._gallery_render()

    def _gallery_thumb(self, slug, size=(190, 118), keep=True):  # the picture of the orientation in use
        """Preview picture of a theme, scaled to fit `size`; None when there is no picture. `keep` stores the
        picture for the gallery; otherwise the caller must hold the reference."""
        try:
            from PIL import Image, ImageTk
            previews = DATA_ROOT / "previews"
            names = [f"{slug}-320x480", slug] if self.settings.orientation == "portrait" else [slug, f"{slug}-320x480"]
            # a theme of the user keeps its picture in its own folder (taken from the running theme, see preview_page)
            own = [theme_paths.custom_dir() / n / "preview.png" for n in names if theme_paths.is_custom(n)]
            path = next((p for p in own if p.is_file()), None) or next(
                (previews / f"{n}.png" for n in names if (previews / f"{n}.png").is_file()), None)
            if path is None:
                return None
            im = Image.open(path).convert("RGB")
            im.thumbnail(size)
            photo = ImageTk.PhotoImage(im)
            if keep:
                self._gallery_images.append(photo)  # keep a reference or Tk drops the picture
            return photo
        except Exception as _e:
            log_swallowed("gallery thumbnail", _e)
            return None

    def gallery_apply(self, slug):
        self.theme_var.set(slug)
        self.on_theme_change()
        self._refresh_dashboard_status()  # not _refresh_dashboard: that starts one more 1 s loop each time
        self._gallery_render()
        # v0.2.4.1: a running Monitor sees the new theme in settings.json and draws it by itself, no restart
        self.toast(f"Applied {slug}")

    def toast(self, text, kind="info"):
        """A small in-app notice that slides in at the bottom right, then leaves (replaces a message box)."""
        old = getattr(self, "_toast", None)
        if old is not None:
            old.destroy()
        accent = PALETTE["crit"] if kind == "error" else PALETTE["green"]
        card = RoundedCard(self.root, PALETTE["bg2"], accent, PALETTE["bg0"], radius=12)
        tk.Label(card.inner, text="\u25cf", bg=PALETTE["bg2"], fg=accent, font=(self.ui_font, 9)).pack(
            side=tk.LEFT, padx=(14, 8), pady=12)
        tk.Label(card.inner, text=text, bg=PALETTE["bg2"], fg=PALETTE["text"], font=(self.ui_font, 10),
                 justify=tk.LEFT, wraplength=340).pack(side=tk.LEFT, padx=(0, 16), pady=12)
        card._fit()
        self._toast_backdrop(card)
        self._toast = card
        for widget in (card, card.inner, *card.inner.winfo_children()):
            widget.bind("<Button-1>", lambda _e: self._toast_leave(card))

        def slide(step, rising):  # ease-out over 10 frames of 15 ms
            if not card.winfo_exists() or self._toast is not card:
                return
            t = step / 10
            offset = round(40 * (1 - (1 - t) ** 2)) if rising else round(40 * t * t)
            card.place(relx=1, rely=1, x=-24, y=-24 + (40 - offset if rising else offset), anchor="se")
            tk.Misc.lift(card)
            if step < 10:
                self.root.after(15, slide, step + 1, rising)
            elif rising:
                card._toast_timer = self.root.after(3200, self._toast_leave, card)
            else:
                card.destroy()
                self._toast = None
        card._slide = slide
        slide(0, True)

    def _toast_backdrop(self, card):
        """Tk has no transparency: the corner pixels of a rounded card are drawn over the canvas colour, which was
        the page's darkest colour. Read the screen just outside the card's four corners and use the most common one."""
        try:
            from PIL import ImageGrab
            self.root.update_idletasks()
            w, h = card.winfo_reqwidth(), card.winfo_reqheight()
            right, bottom = self.root.winfo_rootx() + self.root.winfo_width() - 24, \
                self.root.winfo_rooty() + self.root.winfo_height() - 24
            spots = [(right - w - 1, bottom - h - 1), (right + 1, bottom - h - 1),
                     (right - w - 1, bottom + 1), (right + 1, bottom + 1)]
            shot = ImageGrab.grab((min(x for x, _ in spots), min(y for _, y in spots),
                                   max(x for x, _ in spots) + 1, max(y for _, y in spots) + 1))
            ox, oy = min(x for x, _ in spots), min(y for _, y in spots)
            colours = [shot.getpixel((x - ox, y - oy))[:3] for x, y in spots]
            best = max(set(colours), key=colours.count)
            card.configure(bg="#%02x%02x%02x" % best)
        except Exception as e:  # the page colour stays: only the corners may show a different shade
            log_swallowed("gallery card corner colour", e)

    def _toast_leave(self, card):
        if card.winfo_exists() and self._toast is card and not getattr(card, "_leaving", False):
            card._leaving = True
            card._slide(0, False)

    def gallery_edit(self, slug):
        if not is_editable_theme(slug):  # the built-in themes are not edited; duplicate one to change it
            self.toast("Built-in themes cannot be edited. Duplicate it to make your own copy.")
            return
        self.theme_var.set(slug)
        self.on_theme_change()
        self.select_tab(self.nb.index(self.editor_frame))

    def gallery_duplicate(self, slug):
        """Copy a theme folder (and its portrait variant) to <slug>-copy in the custom themes folder,
        the same place the Theme Editor saves to."""
        import json
        import shutil
        builtin = DATA_ROOT / "themes"
        themes = theme_paths.custom_dir()
        new = f"{slug}-copy"
        n = 2
        while any(theme_paths.folder(builtin, f"{new}{v}").exists() for v in ("", "-320x480")):
            new = f"{slug}-copy{n}"
            n += 1
        made = []
        try:
            themes.mkdir(parents=True, exist_ok=True)
            for variant in ("", "-320x480"):
                src = theme_paths.folder(builtin, f"{slug}{variant}")
                if not src.is_dir():
                    continue
                dst = themes / f"{new}{variant}"
                made.append(dst)  # before the copy: a copy that fails midway is cleaned up too
                shutil.copytree(src, dst)
                meta_path = dst / "theme.json"
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["name"] = f"{meta.get('name', slug)} (copy)"
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as e:
            for folder in made:  # no half-made copy is left behind
                shutil.rmtree(folder, ignore_errors=True)
            self.toast(f"Could not duplicate {slug}: {e}", "error")
            return None
        self.status_var.set(f"Duplicated {slug} as {new}")
        self._gallery_render()
        return new

    def gallery_new(self):
        """New theme: the blank canvas opened as an unsaved draft in the Theme Editor (named custom-<date>)."""
        self.select_tab(self.nb.index(self.editor_frame))
        self.root.update()  # lets the editor start (it is built on the first visit)
        if self.editor_initialized:
            self.theme_editor.start_draft()
        else:
            self.toast("The Theme Editor could not start. See the log.", "error")

    def gallery_import(self):
        """Import theme (.json): open the Theme Editor and use its import."""
        self.select_tab(self.nb.index(self.editor_frame))
        self.root.update()  # lets the editor start (it is built on the first visit)
        if self.editor_initialized:
            self.theme_editor.import_json()
        else:
            self.toast("The Theme Editor could not start. See the log.", "error")
