"""Tk widgets for the v0.2.0 GUI kit, drawn on Canvas because Tk cannot round or style its own.

Look and sizes follow design/v0.2.0 (tokens.css, styles.css, screens.css): card radius 12, control radius 8,
pill 999, 1 px hairlines. Sizes are screen pixels (the app is DPI aware). Every widget takes `backdrop`, the
parent's colour, which shows in the corners.
shortcut: Canvas shapes are not anti-aliased, so curves are slightly stepped; fine at these sizes.
"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from scripts.gui_design import ICON_FONT, PALETTE, mix
from scripts.i18n import tr

P = PALETTE


_corners = {}  # (tk interpreter, radius, fill, border, border width, backdrop) -> four corner PhotoImages


def _corner_images(canvas, r, fill, border, bw):
    """The four r x r corners of a rounded rectangle, drawn at 4x and shrunk so the curve is anti-aliased
    (Tk canvas shapes are not). Order: top-left, top-right, bottom-left, bottom-right."""
    from PIL import Image, ImageColor, ImageDraw, ImageTk
    hard = getattr(canvas, "hard_corners", False)  # a window with a transparent key colour: no half-covered pixels
    key = (id(canvas.tk), r, fill, border, bw, hard)
    if key not in _corners:
        k, rgb = 4, ImageColor.getrgb
        im = Image.new("RGBA", (2 * r * k, 2 * r * k), rgb(border) + (0,))  # same colour at alpha 0: no halo
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, 2 * r * k - 1, 2 * r * k - 1), radius=r * k, fill=rgb(border) + (255,))
        if bw < r:
            d.rounded_rectangle((bw * k, bw * k, (2 * r - bw) * k - 1, (2 * r - bw) * k - 1),
                                radius=(r - bw) * k, fill=rgb(fill) + (255,))
        im = im.resize((2 * r, 2 * r), Image.LANCZOS)
        if hard:  # each pixel is fully the card or fully the key colour (alpha 0 pixels carry the border colour)
            im.putalpha(im.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
        _corners[key] = [ImageTk.PhotoImage(im.crop(box)) for box in
                         ((0, 0, r, r), (r, 0, 2 * r, r), (0, r, r, 2 * r), (r, r, 2 * r, 2 * r))]
    return _corners[key]


def _aa_round_rect(canvas, x1, y1, x2, y2, radius, fill, outline, bw, tags):
    """A rounded rectangle on whole-pixel bounds [x1, x2) x [y1, y2): straight edges from rectangles,
    corners from anti-aliased images. No outline (or bw 0) means the border is the fill colour."""
    w, h = x2 - x1, y2 - y1
    r = int(max(min(radius, w // 2, h // 2), 0))
    if not outline or bw <= 0:
        outline, bw = fill, 1
    bw = min(bw, max(r, 1))
    rect = lambda *c, colour: canvas.create_rectangle(*c, fill=colour, outline="", tags=tags)
    for colour, i in ((outline, 0), (fill, bw)):
        rect(x1 + r, y1 + i, x2 - r, y2 - i, colour=colour)
        if h - 2 * r > 0:
            rect(x1 + i, y1 + r, x2 - i, y2 - r, colour=colour)
    if r:
        for img, (x, y) in zip(_corner_images(canvas, r, fill, outline, bw),
                               ((x1, y1), (x2 - r, y1), (x1, y2 - r), (x2 - r, y2 - r))):
            canvas.create_image(x, y, image=img, anchor="nw", tags=tags)


def text_dy(font):
    """Pixels to add to a label's y so its letters, not its line box, sit in the middle: Tk centres the whole
    line (ascent plus descent), which puts the visible letters about 2 px low in Segoe UI."""
    f = font if isinstance(font, tkfont.Font) else tkfont.Font(font=font)
    m, size = f.metrics(), int(f.cget("size"))
    px = -size if size < 0 else size * tk._default_root.winfo_fpixels("1i") / 72
    return round(0.3 * px - (m["ascent"] - m["descent"]) / 2)


# --- keyboard (v0.2.8) -------------------------------------------------------------------------------------------
# The Canvas widgets are not reached by Tab and show no focus. `focusable` gives a class: a Tab stop (not while its
# state is "disabled"), a cyan ring while it has focus, Space and Return as a click, and the keys in its `_keys`
# ({sequence: function(widget)}). The ring shows only when the last input was a key, as a browser does: a mouse
# click on a field must not leave a ring behind.
_keyboard = [False, False]  # [the last input was a key, the app-wide listeners are installed]


def _draw_ring(w):
    w.delete("ring")
    width, height = w.winfo_width(), w.winfo_height()
    if not (w._focused and _keyboard[0]) or width < 8 or height < 8:
        return
    r = min(getattr(w, "_radius", 10) or height // 2, height // 2)  # _radius None is a pill; most shapes are 10
    x1, y1, x2, y2, d = 1, 1, width - 2, height - 2, 2 * r
    draw = dict(outline=P["cyan"], width=2, tags="ring")
    for box, start in (((x1, y1, x1 + d, y1 + d), 90), ((x2 - d, y1, x2, y1 + d), 0),
                       ((x2 - d, y2 - d, x2, y2), 270), ((x1, y2 - d, x1 + d, y2), 180)):
        w.create_arc(*box, start=start, extent=90, style="arc", **draw)
    for line in ((x1 + r, y1, x2 - r, y1), (x2, y1 + r, x2, y2 - r), (x1 + r, y2, x2 - r, y2), (x1, y1 + r, x1, y2 - r)):
        if line[0] <= line[2] and line[1] <= line[3]:  # a pill has no straight side at its ends
            w.create_line(*line, fill=P["cyan"], width=2, tags="ring")


def _keys_on(widget):
    if not _keyboard[1]:  # once per program: every widget shares these two
        _keyboard[1] = True
        for seq in ("<KeyPress>", "<<NextWindow>>", "<<PrevWindow>>"):  # Tab runs the virtual event, not KeyPress
            widget.bind_all(seq, lambda _e: _keyboard.__setitem__(0, True), add="+")
        widget.bind_all("<ButtonPress>", lambda _e: _keyboard.__setitem__(0, False), add="+")


def focusable(activate=True):
    """Class decorator, see above. `activate=False` for controls that have their own keys (Segmented, Slider)."""
    def wrap(cls):
        init, redraw = cls.__init__, cls._redraw

        def __init__(self, *args, **kw):
            init(self, *args, **kw)
            _keys_on(self)
            # a -takefocus script replaces Tk's own "is it on screen" test, so it must make it (else Tab walks into the
            # pages that are not shown)
            tk.Canvas.configure(self, takefocus=self.register(
                lambda _w: int(str(getattr(self, "_state", "normal")) == "normal" and bool(self.winfo_viewable()))))
            self.bind("<FocusIn>", lambda _e: self._focus(True), add="+")
            self.bind("<FocusOut>", lambda _e: self._focus(False), add="+")
            if activate:
                for seq in ("<space>", "<Return>"):
                    self.bind(seq, lambda _e: self._key_click(), add="+")
            for seq, fn in getattr(self, "_keys", {}).items():
                self.bind(seq, lambda _e, fn=fn: fn(self), add="+")

        def _redraw(self, *args, **kw):
            redraw(self, *args, **kw)
            _draw_ring(self)

        def _focus(self, on):
            self._focused = on
            _draw_ring(self)

        def _key_click(self):
            if str(getattr(self, "_state", "normal")) != "normal":
                return
            x, y = self.winfo_width() // 2, self.winfo_height() // 2
            self.event_generate("<ButtonPress-1>", x=x, y=y)
            self.event_generate("<ButtonRelease-1>", x=x, y=y)
            _keyboard[0] = True  # the generated press counted as the mouse: it was a key
            if self.winfo_exists():
                _draw_ring(self)

        cls._focused = False  # a class default: a widget may redraw inside its own __init__, before the decorator runs
        cls.__init__, cls._redraw, cls._focus, cls._key_click = __init__, _redraw, _focus, _key_click
        return cls
    return wrap


def draw_round_rect(canvas, w, h, radius, fill, outline, width):
    """Rounded rectangle filling a w x h canvas, as the items tagged "bg". radius=None gives a pill."""
    r = h // 2 if radius is None else radius
    canvas.delete("bg")
    _aa_round_rect(canvas, 0, 0, w, h, r, fill, outline, width, "bg")
    canvas.tag_lower("bg")


class RoundedCard(tk.Canvas):
    """A card with rounded corners and a border (Tk frames cannot round). Put the content in
    `.inner`; pack or grid the card itself."""

    def __init__(self, parent, fill, border, backdrop, radius=16, border_w=1, width=None, hard=False):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, width=width or 1, height=1)
        self.hard_corners = hard  # True when `backdrop` is a transparent key colour (see _corner_images)
        self._fill, self._border, self._radius, self._bw = fill, border, radius, border_w
        self._fixed_width = width is not None
        # the square inner frame is inset so its corners stay inside the curve
        self._inset = border_w + int(radius * 0.3)
        self.inner = tk.Frame(self, bg=fill)
        self._win = self.create_window(self._inset, self._inset, anchor="nw", window=self.inner)
        self.bind("<Configure>", self._redraw)
        self.inner.bind("<Configure>", self._fit)

    def _fit(self, _event=None):
        """Ask for the size the content needs; the parent's layout may stretch the card beyond it."""
        pad = 2 * self._inset
        self.inner.update_idletasks()  # a requested size is stale until the pending layout has run
        self.configure(height=self.inner.winfo_reqheight() + pad)
        if not self._fixed_width:
            self.configure(width=self.inner.winfo_reqwidth() + pad)

    def set_border(self, color):
        """Recolour the border (a focus ring)."""
        self._border = color
        draw_round_rect(self, self.winfo_width(), self.winfo_height(), self._radius, self._fill, color, self._bw)

    def _redraw(self, event):
        w, h = event.width, event.height
        draw_round_rect(self, w, h, self._radius, self._fill, self._border, self._bw)
        pad = 2 * self._inset
        self.itemconfigure(self._win, width=max(w - pad, 1), height=max(h - pad, 1))
        # a forced inner size sends no event when the content's request changes: re-ask once idle
        self.after_idle(self._fit)


def fit_cards(widget):
    """v0.3.6.1: give every card under `widget` its height now, while its page is not on screen. A card is fitted when
    its content first reports a size, which only happens once the page is shown: the first visit to each page then drew
    the cards at 1 px and grew them one by one (a flicker, and up to 2 s). Inner cards first."""
    cards = []

    def walk(w):
        for child in w.winfo_children():
            walk(child)
        if isinstance(w, RoundedCard) and not getattr(w, "_prefit", False):
            cards.append(w)
    walk(widget)
    for card in cards:
        card._prefit = True
        card._fit()


@focusable()
class RoundedButton(tk.Canvas):
    """A flat button with rounded corners (Tk buttons cannot round). It takes the options the app
    already changes on a tk.Button: bg (the button's colour), fg, state, text. radius=None gives a pill.
    Hover shows `active_bg` (and `active_fg`). `outline` draws a 1 px border. `disabled` is a
    (bg, fg, outline) tuple for the disabled look; without it only the text colour changes.
    For the design's variants use `make_button`."""

    def __init__(self, parent, text, command, backdrop, bg, fg, active_bg, font, radius=10,
                 padx=14, pady=8, anchor="center", disabled_fg=None, outline=None, active_fg=None,
                 disabled=None, icon=None, icon_dy=0):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0)
        self._icon_dy = icon_dy  # px to move glyph and text down, to centre their ink on the button
        self._icon = (icon[0], tkfont.Font(font=icon[1])) if icon else None  # (glyph, font) left of the text
        self._command, self._radius, self._padx, self._anchor = command, radius, padx, anchor
        self._bg, self._fg, self._active_bg, self._active_fg = bg, fg, active_bg, active_fg
        self._outline, self._disabled = outline, disabled
        self._disabled_fg = disabled_fg or P["dim"]
        self._font, self._text, self._state, self._hover = tkfont.Font(font=font), text, "normal", False
        lines = text.split("\n")
        self._icon_w = self._icon[1].measure(self._icon[0]) + 8 if self._icon else 0
        tk.Canvas.configure(
            self, cursor="hand2",
            width=max(self._font.measure(s) for s in lines) + self._icon_w + 2 * padx,
            height=len(lines) * self._font.metrics("linespace") + 2 * pady)
        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._release)

    def _redraw(self, event=None):
        w, h = self.winfo_width(), self.winfo_height()
        enabled = self._state == "normal"
        hover = self._hover and enabled
        if enabled:
            fill = self._active_bg if hover else self._bg
            outline, fg = self._outline, (self._active_fg if hover and self._active_fg else self._fg)
        elif self._disabled:
            fill, fg, outline = self._disabled
        else:
            fill, outline, fg = self._bg, self._outline, self._disabled_fg
        draw_round_rect(self, w, h, self._radius, fill, outline or fill, 1)
        self.delete("label")
        left = self._anchor in ("w", "nw")
        if self._icon:  # glyph and text as one group, centred
            glyph, gfont = self._icon
            x0 = (w - self._icon_w - self._font.measure(self._text)) / 2
            self.create_text(x0, h / 2 + self._icon_dy + text_dy(gfont), text=glyph, font=gfont, fill=fg, anchor="w", tags="label")
            self.create_text(x0 + self._icon_w, h / 2 + self._icon_dy + text_dy(self._font), text=self._text, font=self._font,
                             fill=fg, anchor="w", tags="label")
            return
        self.create_text(self._padx if left else w / 2, h / 2 + text_dy(self._font), text=self._text, font=self._font,
                         fill=fg, anchor="w" if left else "center",
                         justify="left" if left else "center", tags="label")

    def _set_hover(self, hover):
        self._hover = hover
        self._redraw()

    def _release(self, event):
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        if self._state == "normal" and inside and self._command:
            self._command()

    def configure(self, cnf=None, **kw):
        for key, attr in (("bg", "_bg"), ("fg", "_fg"), ("text", "_text"), ("state", "_state"),
                          ("active_bg", "_active_bg")):
            if key in kw:
                # str(): tk.Button.cget("state") can return a Tcl object that never equals "normal"
                setattr(self, attr, str(kw.pop(key)))
        tk.Canvas.configure(self, cursor="hand2" if self._state == "normal" else "arrow", **kw)
        self._redraw()

    config = configure

    def cget(self, key):
        return self._state if key == "state" else tk.Canvas.cget(self, key)


def rounded_entry(parent, variable, backdrop, font, radius=6):
    """A text field in a rounded card whose border turns cyan while it has focus. Returns (card, entry)."""
    card = RoundedCard(parent, P["bg2"], P["line"], backdrop, radius=radius)
    entry = tk.Entry(card.inner, textvariable=variable, bg=P["bg2"], fg=P["text"], insertbackground=P["text"],
                     relief=tk.FLAT, font=font, highlightthickness=0, bd=0)
    entry.pack(fill=tk.X, padx=8, pady=5, ipady=1)
    entry.bind("<FocusIn>", lambda e: card.set_border(P["cyan"]), add="+")
    entry.bind("<FocusOut>", lambda e: card.set_border(P["line"]), add="+")
    return card, entry


def button_style(variant, backdrop):
    """RoundedButton colour options for a design variant: default, primary, danger or ghost
    (styles.css .btn, .btn-primary, .btn-danger, .btn-ghost; disabled = 40% opacity)."""
    if variant == "primary":
        bg, fg, outline = P["cyan"], P["on_accent"], None
        active_bg, active_fg = mix(bg, "#FFFFFF", 0.88), None
    elif variant == "danger":
        bg, fg, outline = backdrop, P["crit"], mix(P["crit"], backdrop, 0.45)
        active_bg, active_fg = mix(P["crit"], backdrop, 0.14), None
    elif variant == "ghost":
        bg, fg, outline = backdrop, P["muted"], None
        active_bg, active_fg = P["bg3"], P["text"]
    elif variant == "default":
        bg, fg, outline = P["bg2"], P["text"], P["line2"]
        active_bg, active_fg = P["bg3"], None
    else:
        raise ValueError(f"unknown button variant: {variant}")
    off = (mix(bg, backdrop, 0.4), mix(fg, backdrop, 0.4), mix(outline, backdrop, 0.4) if outline else None)
    return dict(bg=bg, fg=fg, active_bg=active_bg, active_fg=active_fg, outline=outline, disabled=off)


def make_button(parent, text, command, font, variant="default", backdrop=None, small=False, **kw):
    """A design button: `variant` default, primary, danger or ghost; `small` is .btn-sm.
    An icon-only button is a glyph as text with font=(ICON_FONT, 12) and padx=9."""
    backdrop = backdrop or P["bg0"]
    opts = button_style(variant, backdrop)
    opts.update(kw)
    if small:
        opts.setdefault("padx", 11)
        opts.setdefault("pady", 6)
    else:
        opts.setdefault("padx", 16)
        opts.setdefault("pady", 9)
    return RoundedButton(parent, text, command, backdrop, font=font, **opts)


@focusable(activate=False)
class Segmented(tk.Canvas):
    """Segmented control (screens.css .seg): options in a rounded tray, the chosen one filled cyan.
    `options` are strings or (value, label) pairs. `variable` (a Tk variable) is kept in step;
    `command(value)` is called when the user picks one."""

    def __init__(self, parent, options, value, command, backdrop, font, variable=None):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, cursor="hand2")
        self._choices = [o if isinstance(o, tuple) else (o, str(o)) for o in options]
        self._value, self._command, self._variable = value, command, variable
        self._font, self._hover, self._spans = tkfont.Font(font=font), None, []
        self._pad_x, self._pad_y, self._tray = 13, 7, 3
        widths = [self._font.measure(label) + 2 * self._pad_x for _v, label in self._choices]
        self._widths = widths
        line = self._font.metrics("linespace")
        tk.Canvas.configure(self, width=sum(widths) + 2 * self._tray + 2,
                            height=line + 2 * self._pad_y + 2 * self._tray + 2)
        if variable is not None:
            self._value = variable.get()
            variable.trace_add("write", lambda *a: self.set(self._variable.get()))
        self._stretch = False
        self.bind("<Configure>", self._on_size)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))

    def get(self):
        return self._value

    def fit_width(self, total):
        """Make the whole control `total` px wide, its segments of one width (so rows of controls line up)."""
        each = (total - 2 * self._tray - 2) / len(self._choices)
        self._widths = [each] * len(self._choices)
        tk.Canvas.configure(self, width=total)

    def stretch(self):
        """Follow the width the parent gives (pack fill=X): equal segments over the full width."""
        self._stretch = True

    def _on_size(self, event):
        if self._stretch and event.width > 2 * self._tray + 2:
            each = (event.width - 2 * self._tray - 2) / len(self._choices)
            self._widths = [each] * len(self._choices)
        self._redraw()

    def set(self, value):
        self._value = value
        self._redraw()

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        draw_round_rect(self, w, h, 10, P["bg2"], P["line2"], 1)
        self.delete("seg")
        self._spans = []
        x, y1, y2 = 1 + self._tray, 1 + self._tray, h - 1 - self._tray
        for (value, label), sw in zip(self._choices, self._widths):
            on = value == self._value
            if on:
                # anti-aliased rounded segment on top of the tray (a smoothed polygon looked jagged)
                _aa_round_rect(self, x, y1, x + sw, y2, 7, P["cyan"], None, 0, "seg")
            fg = P["on_accent"] if on else (P["text"] if value == self._hover else P["muted"])
            self.create_text(x + sw / 2, (y1 + y2) / 2 + text_dy(self._font), text=label, font=self._font, fill=fg, tags="seg")
            self._spans.append((x, x + sw, value))
            x += sw

    def _at(self, x):
        for x1, x2, value in self._spans:
            if x1 <= x < x2:
                return value
        return None

    def _motion(self, event):
        self._set_hover(self._at(event.x))

    def _set_hover(self, value):
        if value != self._hover:
            self._hover = value
            self._redraw()

    def _release(self, event):
        value = self._at(event.x)
        if value is None or not (0 <= event.y < self.winfo_height()):
            return
        self._choose(value)

    def _choose(self, value):
        self._value = value
        if self._variable is not None:
            self._variable.set(value)
        self._redraw()
        if self._command:
            self._command(value)

    def _nudge(self, step):
        """Left and Right keys: the neighbouring option (it stops at the ends)."""
        values = [v for v, _label in self._choices]
        i = values.index(self._value) if self._value in values else 0
        i = min(max(i + step, 0), len(values) - 1)
        if values[i] != self._value:
            self._choose(values[i])

    _keys = {"<Left>": lambda s: s._nudge(-1), "<Right>": lambda s: s._nudge(1)}


@focusable()
class Switch(tk.Canvas):
    """Toggle switch (styles.css .switch, 42 x 24 at 96 dpi, larger on a scaled screen): a pill track and a
    round knob. `variable` (a BooleanVar) is kept in step; `command(on)` is called when the user toggles.
    Off: a dark track and a grey knob on the left. On: a cyan track and a dark knob on the right."""

    W, H = 42, 24
    _radius = None  # the focus ring is a pill

    def __init__(self, parent, value, command, backdrop, variable=None, shrink=1.0):
        """shrink < 1 draws a smaller switch (the sidebar's Theme switch is 0.88)."""
        scale = max(1.0, parent.winfo_fpixels("1i") / 96) * shrink
        self._sw, self._sh = round(self.W * scale), round(self.H * scale)
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, width=self._sw, height=self._sh,
                         cursor="hand2")
        self._value, self._command, self._variable, self._backdrop = bool(value), command, variable, backdrop
        if variable is not None:
            self._value = bool(variable.get())
            variable.trace_add("write", lambda *a: self.set(self._variable.get()))
        self.bind("<ButtonRelease-1>", self._release)
        self._redraw()

    def get(self):
        return self._value

    def set(self, value):
        self._value = bool(value)
        self._redraw()

    _cache = {}  # (on, width, height, backdrop) -> PhotoImage, shared by all switches

    def _image(self):
        """The switch drawn at 4x and shrunk, so its edges are smooth (Tk canvas shapes are not anti-aliased)."""
        from PIL import Image, ImageColor, ImageDraw, ImageTk
        on, w, h = self._value, self._sw, self._sh
        key = (id(self.tk), on, w, h, self._backdrop)  # an image belongs to one Tk interpreter
        if key not in Switch._cache:
            k = 4
            rgb = ImageColor.getrgb
            border = P["cyan"] if on else P["line2"]
            fill = mix(P["cyan"], P["bg1"], 0.55) if on else P["bg0"]
            im = Image.new("RGB", (w * k, h * k), rgb(self._backdrop))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, w * k - 1, h * k - 1), radius=h * k // 2, fill=rgb(border))
            d.rounded_rectangle((k, k, w * k - 1 - k, h * k - 1 - k), radius=(h * k) // 2 - k, fill=rgb(fill))
            knob = (h - 2 * round(h * 0.17)) * k  # leaves about 4 px of track around the knob at 96 dpi
            gap = (h * k - knob) // 2
            x = w * k - gap - knob if on else gap
            d.ellipse((x, gap, x + knob, gap + knob), fill=rgb(P["on_accent"] if on else P["muted"]))
            Switch._cache[key] = ImageTk.PhotoImage(im.resize((w, h), Image.LANCZOS))
        return Switch._cache[key]

    def _redraw(self):
        self.delete("all")
        self.create_image(0, 0, image=self._image(), anchor="nw")

    def _release(self, event):
        if not (0 <= event.x < self._sw and 0 <= event.y < self._sh):
            return
        self._value = not self._value
        if self._variable is not None:
            self._variable.set(self._value)
        self._redraw()
        if self._command:
            self._command(self._value)


@focusable(activate=False)
class Slider(tk.Canvas):
    """Range slider (styles.css input.range): a 4 px track filled cyan up to a 16 px round thumb with
    a soft ring. `variable` (IntVar or DoubleVar) is kept in step; `command(value)` is called while the
    user drags. `step` rounds the value (use 1 for whole numbers)."""

    H, R, PAD = 24, 8, 12

    def __init__(self, parent, from_, to, value, command, backdrop, variable=None, step=1, width=200):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, width=width, height=self.H,
                         cursor="hand2")
        self._from, self._to, self._command = from_, to, command
        self._variable, self._step, self._backdrop = variable, step, backdrop
        self._value = variable.get() if variable is not None else value
        if variable is not None:
            variable.trace_add("write", lambda *a: self.set(self._variable.get()))
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)

    def get(self):
        return self._value

    def set(self, value):
        self._value = min(max(value, self._from), self._to)
        self._redraw()

    def _x_of(self, value, w):
        span = (self._to - self._from) or 1
        return self.PAD + (w - 2 * self.PAD) * (value - self._from) / span

    def _redraw(self):
        w = self.winfo_width()
        if w <= 2 * self.PAD:
            return
        mid, x = self.H / 2, self._x_of(self._value, w)
        self.delete("all")
        self.create_line(self.PAD, mid, w - self.PAD, mid, fill=P["line2"], width=4, capstyle="round")
        self.create_line(self.PAD, mid, x, mid, fill=P["cyan"], width=4, capstyle="round")
        ring = mix(P["cyan"], self._backdrop, 0.22)
        self.create_oval(x - 12, mid - 12, x + 12, mid + 12, fill=ring, outline="")
        self.create_oval(x - self.R, mid - self.R, x + self.R, mid + self.R, fill=P["cyan"], outline="")

    def _drag(self, event):
        w = self.winfo_width()
        if w <= 2 * self.PAD:
            return
        share = min(max((event.x - self.PAD) / (w - 2 * self.PAD), 0), 1)
        value = self._from + share * (self._to - self._from)
        if self._step:
            value = self._from + round((value - self._from) / self._step) * self._step
        self._user_set(value)

    def _user_set(self, value):
        value = min(max(value, self._from), self._to)
        if value == self._value:
            return
        self._value = value
        if self._variable is not None:
            self._variable.set(value)
        self._redraw()
        if self._command:
            self._command(value)

    def _nudge(self, direction):
        """Arrow keys: one step (a hundredth of the range when `step` is 0)."""
        self._user_set(self._value + direction * (self._step or (self._to - self._from) / 100))

    _keys = {"<Left>": lambda s: s._nudge(-1), "<Down>": lambda s: s._nudge(-1),
             "<Right>": lambda s: s._nudge(1), "<Up>": lambda s: s._nudge(1),
             "<Home>": lambda s: s._user_set(s._from), "<End>": lambda s: s._user_set(s._to)}


class Stepper(tk.Frame):
    """A number field in the app's style: the value, then two chevrons (up, down) in a slim column of their own.
    A click steps by one, holding repeats, the wheel and the Up and Down keys step too; the value stays between
    `low` and `high`. `var` is an IntVar the caller listens to."""

    ARROW_W = 22

    def __init__(self, parent, var, low, high, backdrop, font):
        super().__init__(parent, bg=backdrop)
        self._var, self._low, self._high, self._repeat = var, low, high, None
        self.entry = tk.Entry(self, textvariable=var, bg=backdrop, fg=P["text"], insertbackground=P["text"],
                              relief=tk.FLAT, highlightthickness=0, font=font, width=1)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 4), ipady=4)
        self._arrows = tk.Canvas(self, width=self.ARROW_W, height=1, bg=backdrop, highlightthickness=0, bd=0,
                                 cursor="hand2")
        self._arrows.pack(side=tk.RIGHT, fill=tk.Y)
        self._hot = None
        self._arrows.bind("<Configure>", lambda _e: self._draw())
        self._arrows.bind("<Motion>", lambda e: self._set_hot(self._which(e)))
        self._arrows.bind("<Leave>", lambda _e: self._set_hot(None))
        self._arrows.bind("<ButtonPress-1>", self._press)
        self._arrows.bind("<ButtonRelease-1>", lambda _e: self._stop())
        for w in (self.entry, self._arrows):
            w.bind("<MouseWheel>", lambda e: (self.step(1 if e.delta > 0 else -1), "break")[1])
        self.entry.bind("<Up>", lambda _e: (self.step(1), "break")[1])
        self.entry.bind("<Down>", lambda _e: (self.step(-1), "break")[1])

    def _which(self, event):
        return 1 if event.y < self._arrows.winfo_height() / 2 else -1

    def _set_hot(self, which):
        if which != self._hot:
            self._hot = which
            self._draw()

    def _draw(self):
        c, w, h = self._arrows, self._arrows.winfo_width(), self._arrows.winfo_height()
        c.delete("all")
        c.create_line(0, 5, 0, h - 5, fill=P["line2"])  # the divider
        for direction, cy in ((1, h * 0.27), (-1, h * 0.73)):
            colour = P["cyan"] if self._hot == direction else P["muted"]
            x = w / 2 + 1
            c.create_line(x - 4, cy + 2 * direction, x, cy - 2 * direction, x + 4, cy + 2 * direction, fill=colour,
                          width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND)

    def step(self, delta):
        try:
            value = int(self._var.get())
        except (tk.TclError, ValueError):
            value = self._low
        self._var.set(max(self._low, min(self._high, value + delta)))

    def _press(self, event):
        delta = self._which(event)
        self.step(delta)
        self._stop()
        self._repeat = self.after(400, lambda: self._hold(delta))

    def _hold(self, delta):
        self.step(delta)
        self._repeat = self.after(60, lambda: self._hold(delta))

    def _stop(self):
        if self._repeat is not None:
            self.after_cancel(self._repeat)
            self._repeat = None


class SelectList(tk.Toplevel):
    """The open list of a Select: a rounded card as wide as the field, rows with a hover tint and a check on the
    chosen one, at most `MAX_ROWS` rows high; a longer list scrolls (wheel, slim bar)."""

    ROW, MAX_ROWS, PAD = 36, 6, 6

    def __init__(self, field, values, current, pick, font, on_close, align="left"):
        super().__init__(field)
        self._align = align
        self.overrideredirect(True)
        self.configure(bg=P["line2"])
        self._values, self._current, self._pick, self._font, self._on_close = values, current, pick, font, on_close
        self._hover = None
        n = max(len(values), 1)
        self._wd = max(field.winfo_width(), 120)
        self._ht = min(n, self.MAX_ROWS) * self.ROW + 2 * self.PAD
        self._total = n * self.ROW + 2 * self.PAD
        self._cv = tk.Canvas(self, width=self._wd - 2, height=self._ht, bg=P["bg2"], highlightthickness=0, bd=0)
        self._cv.pack(padx=1, pady=1)
        self._cv.configure(scrollregion=(0, 0, self._wd - 2, self._total))
        x, y = field.winfo_rootx(), field.winfo_rooty() + field.winfo_height() + 4
        if y + self._ht + 2 > self.winfo_screenheight():  # no room below: open above the field
            y = field.winfo_rooty() - self._ht - 6
        self.geometry(f"{self._wd}x{self._ht + 2}+{x}+{y}")
        self._draw()
        if self._current in values:  # the chosen row in view
            self._cv.yview_moveto(max(0, values.index(self._current) * self.ROW - self.ROW) / self._total)
            self._bar()
        self._cv.bind("<Motion>", self._motion)
        self._cv.bind("<Leave>", lambda _e: self._set_hover(None))
        self._cv.bind("<ButtonRelease-1>", self._release)
        self._cv.bind("<MouseWheel>", self._wheel)
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<Down>", lambda _e: self._move(1))
        self.bind("<Up>", lambda _e: self._move(-1))
        self.bind("<Home>", lambda _e: self._move(-len(self._values)))
        self.bind("<End>", lambda _e: self._move(len(self._values)))
        for seq in ("<Return>", "<space>"):
            self.bind(seq, lambda _e: self._choose_hovered())
        self.bind("<Button-1>", self._outside)
        self.update_idletasks()
        self.focus_force()
        self.grab_set()  # a click anywhere else closes the list

    def _index(self, event):
        i = int((self._cv.canvasy(event.y) - self.PAD) // self.ROW)
        return i if 0 <= i < len(self._values) else None

    def _draw(self):
        cv, w = self._cv, self._wd - 2
        cv.delete("all")
        for i, value in enumerate(self._values):
            top = self.PAD + i * self.ROW
            chosen = value == self._current
            if i == self._hover or chosen:
                draw_row = P["bg3"] if i == self._hover else mix(P["cyan"], P["bg2"], 0.12)
                self._round(cv, 6, top + 2, w - 6, top + self.ROW - 2, 8, draw_row)
            centred = self._align == "center"
            cv.create_text(w / 2 if centred else 16, top + self.ROW / 2 + text_dy(self._font), text=str(value),
                           font=self._font, anchor="center" if centred else "w",
                           fill=P["cyan"] if chosen else P["text"])
            if chosen:
                cv.create_text(w - 18, top + self.ROW / 2, text="✓", font=self._font, fill=P["cyan"])
        if not self._values:
            cv.create_text(16, self.PAD + self.ROW / 2, text="Nothing to choose", font=self._font, anchor="w",
                           fill=P["muted"])
        self._bar()

    @staticmethod
    def _round(cv, x1, y1, x2, y2, r, fill):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2,
               x1, y2 - r, x1, y1 + r, x1, y1]
        cv.create_polygon(pts, smooth=True, fill=fill, outline="")

    def _bar(self):
        cv = self._cv
        cv.delete("bar")
        if self._total <= self._ht:
            return
        top = cv.canvasy(0)
        t0, t1 = top + self._ht * top / self._total, top + self._ht * (top + self._ht) / self._total
        cv.create_rectangle(self._wd - 8, t0 + 3, self._wd - 5, t1 - 3, fill=P["line2"], outline="", tags="bar")

    def _set_hover(self, i):
        if i != self._hover:
            self._hover = i
            self._draw()

    def _motion(self, event):
        self._set_hover(self._index(event))

    def _move(self, step):
        """Up, Down, Home, End: the highlighted row, scrolled into view. From nothing, Down starts at the chosen row."""
        n = len(self._values)
        if not n:
            return
        if self._hover is None:
            start = self._values.index(self._current) if self._current in self._values else (-1 if step > 0 else n)
        else:
            start = self._hover
        i = min(max(start + step, 0), n - 1)
        self._set_hover(i)
        top, view = self.PAD + i * self.ROW, self._cv.canvasy(0)
        if top < view:
            self._cv.yview_moveto(max(top - self.PAD, 0) / self._total)
        elif top + self.ROW > view + self._ht:
            self._cv.yview_moveto((top + self.ROW + self.PAD - self._ht) / self._total)
        self._bar()

    def _choose_hovered(self):
        if self._hover is not None:
            value = self._values[self._hover]
            self.close()
            self._pick(value)

    def _wheel(self, event):
        if self._total > self._ht:
            self._cv.yview_scroll(-1 if event.delta > 0 else 1, "units")
            self._cv.yview_scroll(0, "units")
            self._bar()
        return "break"  # the page behind the list must not scroll

    def _release(self, event):
        i = self._index(event)
        if i is not None:
            value = self._values[i]
            self.close()
            self._pick(value)

    def _outside(self, event):
        if event.widget is self or not str(event.widget).startswith(str(self)):
            self.close()

    def close(self):
        if self.winfo_exists():
            self.grab_release()
            self.destroy()
            self._on_close()


@focusable()
class Select(tk.Canvas):
    """Dark drop-down (styles.css select.input): a rounded field with a caret; a click opens a menu.
    `variable` (StringVar) is kept in step; `command(value)` is called when the user picks one."""

    def __init__(self, parent, values, value, command, backdrop, font, variable=None, width=200, align="left"):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, cursor="hand2", width=width)
        self._align = align  # "center": the value and the list's rows are centred
        self._values, self._command, self._variable, self._font = values, command, variable, font
        self._value, self._open = value, False
        self._measure = tkfont.Font(font=font)
        tk.Canvas.configure(self, height=self._measure.metrics("linespace") + 2 * 9 + 2)
        if variable is not None:
            self._value = variable.get()
            variable.trace_add("write", lambda *a: self.set(self._variable.get()))
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<ButtonRelease-1>", self._release)

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        self._redraw()

    def set_values(self, values):
        self._values = values

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        draw_round_rect(self, w, h, 10, P["bg0"], P["cyan"] if self._open else P["line2"], 1)
        self.delete("label")
        centred = self._align == "center"
        self.create_text(w / 2 if centred else 12, h / 2 + text_dy(self._font), text=str(self._value),
                         font=self._font, fill=P["text"], anchor="center" if centred else "w", tags="label")
        cx, cy = w - 16, h / 2
        self.create_polygon(cx - 4, cy - 2, cx + 4, cy - 2, cx, cy + 3, fill=P["muted"], outline="",
                            tags="label")

    def _release(self, event):
        if not (0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()):
            return
        self._open_list()

    def _open_list(self):
        if self._open:
            return
        self._open = True
        self._redraw()
        SelectList(self, self.values(), self._value, self._pick, self._font, self._closed, self._align)

    def _closed(self):
        self._open = False
        self._redraw()
        self.focus_set()  # the list took the focus: give it back, so the keyboard carries on from this field

    _keys = {"<Down>": lambda s: s._open_list(), "<Up>": lambda s: s._open_list()}

    def values(self):
        """The choices now: `values` may be a function, so a list that grows (new themes) is read when it opens."""
        return list(self._values() if callable(self._values) else self._values)

    def _pick(self, value):
        self._value = value
        if self._variable is not None:
            self._variable.set(value)
        self._redraw()
        if self._command:
            self._command(value)


class StatRow(RoundedCard):
    """A list row (screens.css .sensor-row): a name on the left, a mono value and a status dot on the
    right, in a small rounded card. Used for sensors and other live lists."""

    def __init__(self, parent, name, backdrop, font, mono_font):
        super().__init__(parent, P["bg2"], P["line"], backdrop, radius=10)
        row = self.inner
        # dot and value are packed first: in a narrow row (high scaling) Tk squeezes the last one packed, and it is
        # the name that may lose a few letters, not the number
        self._dot = tk.Label(row, text="●", bg=P["bg2"], fg=P["dim"], font=(font[0], 8))
        self._dot.pack(side=tk.RIGHT, padx=(6, 8))
        self._value = tk.Label(row, text="", bg=P["bg2"], fg=P["text"], font=mono_font, anchor="e")
        self._value.pack(side=tk.RIGHT)
        tk.Label(row, text=name, bg=P["bg2"], fg=P["text"], font=font, anchor="w").pack(
            side=tk.LEFT, padx=(8, 0), pady=6)

    def set_value(self, text):
        self._value.config(text=text)

    def set_status(self, colour):
        self._dot.config(fg=colour)


def page_header(parent, title, subtitle, backdrop, title_font, text_font):
    """Screen head (styles.css .screen-head): a title and a muted line, with `.actions` on the right
    for the screen's buttons."""
    head = tk.Frame(parent, bg=backdrop)
    left = tk.Frame(head, bg=backdrop)
    left.pack(side=tk.LEFT, fill=tk.X, expand=True)
    tk.Label(left, text=title, bg=backdrop, fg=P["text"], font=title_font, anchor="w").pack(fill=tk.X)
    if subtitle:
        tk.Label(left, text=subtitle, bg=backdrop, fg=P["muted"], font=text_font, anchor="w",
                 justify=tk.LEFT).pack(fill=tk.X, pady=(2, 0))
    head.actions = tk.Frame(head, bg=backdrop)
    head.actions.pack(side=tk.RIGHT, anchor="s")
    return head


@focusable()
class NavItem(tk.Canvas):
    """Sidebar entry (styles.css .nav-item): glyph and label in a rounded row; the active one has a
    tinted fill and a cyan bar on the left edge. `command()` is called on click."""

    H = 40

    def __init__(self, parent, glyph, text, command, backdrop, icon_font, font):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, height=self.H, cursor="hand2")
        self._glyph, self._text, self._command, self._backdrop = glyph, text, command, backdrop
        self._icon_font, self._font = icon_font, font
        self._active = self._hover = False
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._release)

    @property
    def active(self):
        return self._active

    def set_active(self, active):
        if bool(active) == self._active:
            return  # v0.2.4: a page switch redrew all nine entries twice
        self._active = bool(active)
        self._redraw()

    def _set_hover(self, hover):
        self._hover = hover
        self._redraw()

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        if self._active:
            draw_round_rect(self, w, h, 12, mix(P["cyan"], self._backdrop, 0.13), "", 0)
            self.create_polygon(0, h / 2 - 9, 3, h / 2 - 9, 3, h / 2 + 9, 0, h / 2 + 9,
                                fill=P["cyan"], outline="")
        elif self._hover:
            draw_round_rect(self, w, h, 12, P["bg3"], P["bg3"], 1)
        fg = P["text"] if self._active or self._hover else P["muted"]
        self.create_text(12 + 10, h / 2, text=self._glyph, font=self._icon_font,
                         fill=P["cyan"] if self._active else fg)
        self.create_text(12 + 20 + 12, h / 2 + text_dy(self._font), text=self._text, font=self._font, fill=fg, anchor="w")

    def _release(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height() and self._command:
            self._command()


class DeviceChip(RoundedCard):
    """Sidebar footer card (styles.css .device-card): a status dot, a small DEVICE label and the
    device name in mono. `set_status(text, level)` with level "ok", "busy" or "off"."""

    DOT = {"ok": "green", "busy": "warn", "off": "dim"}

    def __init__(self, parent, backdrop, font, mono_font, logo=None):
        super().__init__(parent, P["bg2"], P["line"], backdrop, radius=16)
        if logo is not None:  # a PhotoImage, centred on the right with a margin
            tk.Label(self.inner, image=logo, bg=P["bg2"], bd=0).pack(side=tk.RIGHT, padx=(6, 12))
        text = tk.Frame(self.inner, bg=P["bg2"])
        text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        top = tk.Frame(text, bg=P["bg2"])
        top.pack(fill=tk.X, padx=4, pady=(6, 0))
        self._dot = tk.Label(top, text="●", bg=P["bg2"], fg=P["dim"], font=(font[0], 8))
        self._dot.pack(side=tk.LEFT)
        tk.Label(top, text=tr("DEVICE"), bg=P["bg2"], fg=P["muted"], font=font).pack(side=tk.LEFT, padx=(6, 0))
        self._info = tk.Label(text, text="", bg=P["bg2"], fg=P["text"], font=mono_font, anchor="w")
        self._info.pack(fill=tk.X, padx=4, pady=(6, 6))

    def set_status(self, text, level):
        self._dot.config(fg=P[self.DOT.get(level, "dim")])
        self._info.config(text=text)


class Badge(tk.Canvas):
    """Small pill with a tinted fill (styles.css .badge): `set(text, colour)` recolours it."""

    def __init__(self, parent, backdrop, font, solid=False):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, width=1, height=1)
        self._backdrop, self._font, self._solid = backdrop, tkfont.Font(font=font), solid
        self._text, self._colour = "", P["muted"]
        self.bind("<Configure>", lambda e: self._redraw())

    def set(self, text, colour):
        if (text, colour) == (self._text, self._colour):
            return
        self._text, self._colour = text, colour
        tk.Canvas.configure(self, width=self._font.measure(text) + 20, height=self._font.metrics("linespace") + 6)
        self._redraw()

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        fill = self._colour if self._solid else mix(self._colour, self._backdrop, 0.16)
        draw_round_rect(self, w, h, None, fill, fill, 1)
        self.delete("label")
        self.create_text(w / 2, h / 2 + text_dy(self._font), text=self._text, font=self._font,
                         fill=P["on_accent"] if self._solid else self._colour, tags="label")


@focusable()
class ControlButton(tk.Canvas):
    """Dashboard control (screens.css .ctrl-btn): a card-shaped button with an icon tile at the top left,
    then a title and a subtitle. `tint` colours the tile (None = cyan glyph on a neutral tile). Disabled is
    45% opacity. Takes `state` and `command` like RoundedButton."""

    PAD, TILE = 12, 32

    def __init__(self, parent, glyph, title, sub, command, backdrop, tint, icon_font, title_font, sub_font):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, cursor="hand2")
        self._glyph, self._title, self._sub, self._command = glyph, title, sub, command
        self._backdrop, self._tint, self._state, self._hover = backdrop, tint, "normal", False
        self._icon_font, self._title_font, self._sub_font = (tkfont.Font(font=f) for f in (icon_font, title_font, sub_font))
        tk.Canvas.configure(self, height=2 * self.PAD + self.TILE + 10 + self._title_font.metrics("linespace")
                            + self._sub_font.metrics("linespace") + 2,
                            width=2 * self.PAD + max(self._title_font.measure(title), self._sub_font.measure(sub)))
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._release)

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        on = self._state == "normal"
        fade = (lambda c: c) if on else (lambda c: mix(c, self._backdrop, 0.45))
        border = mix(P["cyan"], P["line2"], 0.4) if self._hover and on else P["line2"]
        draw_round_rect(self, w, h, 16, fade(P["bg2"]), fade(border), 1)
        self.delete("content")
        tile = P["bg3"] if self._tint is None else mix(self._tint, P["bg2"], 0.16)
        glyph = P["cyan"] if self._tint is None else self._tint
        x, y, t = self.PAD, self.PAD, self.TILE
        self.create_polygon(x + 10, y, x + t - 10, y, x + t, y, x + t, y + 10, x + t, y + t - 10, x + t, y + t,
                            x + t - 10, y + t, x + 10, y + t, x, y + t, x, y + t - 10, x, y + 10, x, y,
                            smooth=True, fill=fade(tile), outline=fade(tile), tags="content")
        self.create_text(x + t / 2, y + t / 2, text=self._glyph, font=self._icon_font, fill=fade(glyph), tags="content")
        ty = y + t + 10
        self.create_text(x, ty, text=self._title, font=self._title_font, fill=fade(P["text"]), anchor="nw", tags="content")
        self.create_text(x, ty + self._title_font.metrics("linespace"), text=self._sub, font=self._sub_font,
                         fill=fade(P["muted"]), anchor="nw", tags="content")

    def _set_hover(self, hover):
        self._hover = hover
        self._redraw()

    def _release(self, event):
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        if self._state == "normal" and inside and self._command:
            self._command()

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._state = str(kw.pop("state"))  # str(): tk.Button.cget("state") can return a Tcl object
        tk.Canvas.configure(self, cursor="hand2" if self._state == "normal" else "arrow", **kw)
        self._redraw()

    config = configure

    def cget(self, key):
        return self._state if key == "state" else tk.Canvas.cget(self, key)


def draw_spark(canvas, points, colour, backdrop):
    """History line with a soft fill under it (design .sc-spark). `points` are x0, y0, x1, y1, ... as from
    sparkline_points; an empty list clears the canvas."""
    canvas.delete("all")
    if len(points) < 4:
        return
    bottom = max(canvas.winfo_height(), 10) - 1
    canvas.create_polygon(*points, points[-2], bottom, points[0], bottom, fill=mix(colour, backdrop, 0.16), outline="")
    canvas.create_line(*points, fill=colour, width=2, smooth=True)


def round_rect(canvas, x1, y1, x2, y2, radius, fill="", outline="", width=1):
    """An anti-aliased rounded rectangle at any position (draw_round_rect fills a whole canvas instead)."""
    _aa_round_rect(canvas, round(x1), round(y1), round(x2), round(y2), radius, fill, outline, width, "rr")


@focusable()
class WidgetTile(tk.Canvas):
    """Theme Editor palette tile (screens.css .widget-tile): a glyph, the widget name and a muted line,
    centred in a rounded tile. A click calls `command()`; hover lights the border."""

    H = 84

    def __init__(self, parent, glyph, title, sub, command, backdrop, card, icon_font, title_font, sub_font):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, width=1, height=self.H, cursor="hand2")
        self._glyph, self._title, self._sub, self._command, self._card = glyph, title, sub, command, card
        self._fonts, self._hover = (icon_font, title_font, sub_font), False
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._release)

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        draw_round_rect(self, w, h, 10, P["bg3"] if self._hover else self._card,
                        P["cyan"] if self._hover else P["line"], 1)
        self.delete("content")
        icon, title, sub = self._fonts
        self.create_text(w / 2, 22, text=self._glyph, font=icon, fill=P["cyan"], tags="content")
        self.create_text(w / 2, 46, text=self._title, font=title, fill=P["text"], tags="content")
        self.create_text(w / 2, 65, text=self._sub, font=sub, fill=P["muted"], tags="content")

    def _set_hover(self, hover):
        self._hover = hover
        self._redraw()

    def _release(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height() and self._command:
            self._command()


@focusable()
class IconTile(tk.Canvas):
    """One icon of the icon picker: its picture over its name; the chosen one has the accent border."""

    W, H = 84, 78

    def __init__(self, parent, photo, name, selected, command, backdrop, card, name_font):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, width=self.W, height=self.H, cursor="hand2")
        self._photo, self._name, self._selected, self._command = photo, name, selected, command
        self._card, self._font, self._hover = card, name_font, False
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._release)

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        fill = mix(P["cyan"], self._card, 0.12) if self._selected else (P["bg3"] if self._hover else self._card)
        border = P["cyan"] if self._selected else (P["line2"] if self._hover else P["line"])
        draw_round_rect(self, w, h, 10, fill, border, 1)
        self.delete("content")
        self.create_image(w / 2, h / 2 - 9, image=self._photo, tags="content")
        self.create_text(w / 2, h - 13 + text_dy(self._font), text=self._name, font=self._font,
                         fill=P["cyan"] if self._selected else P["muted"], tags="content")

    def _set_hover(self, hover):
        self._hover = hover
        self._redraw()

    def _release(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height() and self._command:
            self._command()


@focusable()
class LayerRow(tk.Canvas):
    """One widget of the theme in the Theme Editor's list: its type glyph, its name and its type. The chosen
    row has the accent border; a click calls `command()`. `movers` = (up, down) callbacks, each a function or None when
    that move is not possible: the chosen row then shows two bare arrows at its right edge instead of the type."""

    H = 38
    ARROW_UP, ARROW_DOWN = "", ""  # Segoe MDL2 chevrons

    def __init__(self, parent, glyph, name, kind, selected, command, backdrop, card, icon_font, name_font, kind_font,
                 movers=None):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, width=1, height=self.H, cursor="hand2")
        self._glyph, self._name, self._kind, self._selected = glyph, name, kind, selected
        self._command, self._card, self._hover = command, card, False
        self._movers, self._arrow = movers if selected else None, None  # _arrow: the arrow under the pointer
        self._fonts = (icon_font, name_font, kind_font)
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: (self._set_arrow(None), self._set_hover(False)))
        self.bind("<Motion>", lambda e: self._set_arrow(self._arrow_at(e.x, e.y)))
        self.bind("<ButtonRelease-1>", self._release)

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        fill = P["bg0"] if self._selected else (P["bg3"] if self._hover else self._card)
        border = P["cyan"] if self._selected else (P["line2"] if self._hover else P["line"])
        draw_round_rect(self, w, h, 8, fill, border, 1)
        self.delete("content")
        icon, name, kind = self._fonts
        self.create_text(18, h / 2, text=self._glyph, font=icon, fill=P["cyan"], tags="content")
        self.create_text(36, h / 2 + text_dy(name), text=self._name, font=name, fill=P["text"], anchor="w",
                         tags="content")
        if self._movers:  # bare arrows, grey when that move is not possible, cyan under the pointer
            for which, glyph in (("up", self.ARROW_UP), ("down", self.ARROW_DOWN)):
                usable = self._movers[0 if which == "up" else 1] is not None
                colour = P["line2"] if not usable else (P["cyan"] if self._arrow == which else P["muted"])
                self.create_text(self._arrow_x(which, w), h / 2, text=glyph, font=(ICON_FONT, 10), fill=colour,
                                 tags="content")
        elif 36 + tkfont.Font(font=name).measure(self._name) + 10 + tkfont.Font(font=kind).measure(self._kind) < w - 10:
            self.create_text(w - 10, h / 2 + text_dy(kind), text=self._kind, font=kind, fill=P["muted"], anchor="e",
                             tags="content")  # the type is dropped when a long name needs the room

    def _set_hover(self, hover):
        self._hover = hover
        self._redraw()

    @staticmethod
    def _arrow_x(which, width):
        return width - 14 if which == "down" else width - 38  # 10 px from the edge, 10 px between the glyphs

    def _arrow_at(self, x, y):
        """"up", "down" or None: the arrow under (x, y), a 24 px wide square around each glyph."""
        if not self._movers or not 0 <= y < self.H:
            return None
        w = self.winfo_width()
        return next((which for which in ("up", "down") if abs(x - self._arrow_x(which, w)) <= 12), None)

    def _set_arrow(self, which):
        if which != self._arrow:
            self._arrow = which
            self._redraw()

    def _release(self, event):
        if not (0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()):
            return
        which = self._arrow_at(event.x, event.y)
        if which:  # an arrow: move, or nothing when that move is not possible; never a re-selection
            move = self._movers[0 if which == "up" else 1]
            if move:
                move()
        elif self._command:
            self._command()


@focusable()
class ChoiceTile(tk.Canvas):
    """A choice among several (one is selected): the name on the left and a check on the right when
    selected. The selected tile is darker with an accent border; the others are raised."""

    H = 44

    def __init__(self, parent, text, selected, command, backdrop, font, icon_font=("Segoe MDL2 Assets", 11),
                 swatches=()):
        """`swatches`: colours drawn as small blocks after the name and a dot ("name · [palette]")."""
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, width=1, height=self.H, cursor="hand2")
        self._swatches = tuple(swatches)
        self._text, self._selected, self._command, self._fonts, self._hover = text, selected, command, (font, icon_font), False
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._release)

    def set_selected(self, selected):
        self._selected = selected
        self._redraw()

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        if self._selected:
            fill, border = P["bg0"], P["cyan"]
        else:
            fill, border = (P["bg3"], P["muted"]) if self._hover else (P["bg3"], P["line2"])
        draw_round_rect(self, w, h, 10, fill, border, 1)
        self.delete("content")
        font, icon = self._fonts
        label = self._text + ("  \u00b7" if self._swatches else "")
        item = self.create_text(16, h / 2 + text_dy(font), text=label, font=font, fill=P["text"], anchor="w", tags="content")
        if self._swatches:  # three thin bars from after the name to 40 px short of the right edge (the check's room)
            x0, x1 = self.bbox(item)[2] + 8, w - 40
            each = (x1 - x0 - 2 * 3) / 3
            for i, colour in enumerate(self._swatches):
                x = x0 + i * (each + 3)
                self.create_rectangle(x, h / 2 - 2, x + each, h / 2 + 2, fill=colour, outline="", tags="content")
        if self._selected:
            self.create_text(w - 18, h / 2, text="\uE73E", font=icon, fill=P["cyan"], tags="content")

    def _set_hover(self, hover):
        self._hover = hover
        self._redraw()

    def _release(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height() and self._command:
            self._command()


@focusable()
class ThemeChip(tk.Canvas):
    """Quick-theme chip (screens.css .quick-theme-btn): a coloured dot and the theme name. The active
    one has a cyan border and an 8% cyan tint; hover tints with the theme's own colour."""

    H = 40

    def __init__(self, parent, label, dot, command, backdrop, card, font):
        super().__init__(parent, bg=backdrop, highlightthickness=0, bd=0, width=1, height=self.H, cursor="hand2")
        self._label, self._dot, self._command, self._card = label, dot, command, card
        self._font, self._active, self._hover = tkfont.Font(font=font), False, False
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._release)

    @property
    def active(self):
        return self._active

    def set_active(self, active):
        if active != self._active:
            self._active = active
            self._redraw()

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        fill = mix(self._dot, self._card, 0.10) if self._hover else (
            mix(P["cyan"], self._card, 0.08) if self._active else self._card)
        border = P["cyan"] if self._active else (self._dot if self._hover else P["line"])
        draw_round_rect(self, w, h, 10, fill, border, 1)
        self.delete("content")
        self.create_oval(12, h / 2 - 5, 22, h / 2 + 5, fill=self._dot, outline=self._dot, tags="content")
        text, room = self._label, w - 30 - 12
        while len(text) > 1 and self._font.measure(text) > room:  # too long for the chip: cut with an ellipsis
            text = text[:-1]
        if text != self._label:
            text = text.rstrip() + "\u2026"
        self.create_text(30, h / 2 + text_dy(self._font), text=text, font=self._font, fill=P["text"], anchor="w", tags="content")

    def _set_hover(self, hover):
        self._hover = hover
        self._redraw()

    def _release(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height() and self._command:
            self._command()


class Tip:
    """A hover tooltip (v0.2.6.1). `text` is a function called on hover: it returns the sentence to show, or "" for
    no tooltip (so one binding serves a value that sometimes has a reading). Shown after DELAY ms, under the widget,
    in the card colours; hidden on leave, click or destroy."""
    DELAY = 400
    RECHECK = 500

    def __init__(self, widget, text):
        self._w, self._text, self._job, self._tip = widget, text, None, None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _enter(self, _event=None):
        self._hide()
        self._job = self._w.after(self.DELAY, self._show)

    def _show(self):
        self._job = None
        tip = None
        try:
            text = self._text()
            if not text or not self._w.winfo_exists() or not self._w.winfo_viewable():
                return
            tip = tk.Toplevel(self._w)
            tip.wm_overrideredirect(True)
            tip.attributes("-topmost", True)
            frame = tk.Frame(tip, bg=PALETTE["line"], padx=1, pady=1)
            frame.pack()
            tk.Label(frame, text=text, bg=PALETTE["bg3"], fg=PALETTE["text"], font=("Segoe UI", 9), justify=tk.LEFT,
                     wraplength=280, padx=8, pady=5).pack()
            x = self._w.winfo_rootx()
            y = self._w.winfo_rooty() + self._w.winfo_height() + 6
            tip.update_idletasks()
            x = max(0, min(x, self._w.winfo_screenwidth() - tip.winfo_reqwidth() - 8))  # stay on the screen
            tip.wm_geometry(f"+{x}+{y}")
            self._tip = tip
            self._job = self._w.after(self.RECHECK, self._recheck)
        except tk.TclError:  # ok: the widget went away while the tip was opening
            if tip is not None:
                try:
                    tip.destroy()
                except tk.TclError:  # ok: already gone
                    pass
            self._tip = None

    def _recheck(self):
        """While the tip is up: close it when the reason is gone (the value arrived) or the widget is hidden
        (the pointer did not leave, so no Leave event came)."""
        self._job = None
        try:
            if self._tip is None:
                return
            if not self._text() or not self._w.winfo_viewable():
                self._hide()
            else:
                self._job = self._w.after(self.RECHECK, self._recheck)
        except tk.TclError:  # ok: the widget is being destroyed
            self._hide()

    def _hide(self, _event=None):
        try:
            if self._job is not None:
                self._w.after_cancel(self._job)
        except tk.TclError:  # ok: the widget is already gone
            pass
        self._job = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:  # ok: already destroyed
                pass
            self._tip = None


class ScrollFrame(tk.Frame):
    """A frame that scrolls vertically when its content is taller than the window (the design's pages
    scroll). Put the content in `.body`; the scrollbar shows only when needed. The mouse wheel scrolls
    while the pointer is over this frame."""

    def __init__(self, parent, bg, stretch=False, bar_gap=0):
        """bar_gap is the space between the content and the scroll bar. stretch=True makes the body at least as tall as the window, so a page whose content is static can
        fill it (a later change in the content's size sends no event, so the bar would not follow)."""
        super().__init__(parent, bg=bg)
        self._stretch, self._bar_gap = stretch, bar_gap
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._bar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._bar.set)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.body = tk.Frame(self._canvas, bg=bg)
        self._win = self._canvas.create_window(0, 0, anchor="nw", window=self.body)
        self.body.bind("<Configure>", self._on_body)
        self._canvas.bind("<Configure>", self._on_canvas)
        self.bind_all("<MouseWheel>", self._wheel, add="+")
        self.bind_all("<FocusIn>", self._reveal, add="+")

    def _reveal(self, event):
        """Tab to a control below or above the visible part of the page: scroll it into view (v0.2.8)."""
        w = event.widget
        try:
            if not str(w).startswith(str(self.body) + ".") or not self._canvas.winfo_ismapped():
                return
            top = w.winfo_rooty() - self.body.winfo_rooty()
            bottom = top + w.winfo_height()
            view, shown, total = self._canvas.canvasy(0), self._canvas.winfo_height(), self.body.winfo_reqheight()
            if total <= shown:
                return
            if top < view:
                self._canvas.yview_moveto(max(top - 12, 0) / total)
            elif bottom > view + shown:
                self._canvas.yview_moveto(min(bottom + 12 - shown, total - shown) / total)
        except tk.TclError:
            pass

    def _needs_bar(self):
        return self.body.winfo_reqheight() > self._canvas.winfo_height() > 1

    def _on_body(self, _event=None):
        self._canvas.configure(scrollregion=(0, 0, self.body.winfo_reqwidth(), self.body.winfo_reqheight()))
        self._stretch_body()
        self._sync_bar()

    def _stretch_body(self):
        if self._stretch:
            self._canvas.itemconfigure(self._win, height=max(self._canvas.winfo_height(), self.body.winfo_reqheight()))

    def _on_canvas(self, event):
        self._canvas.itemconfigure(self._win, width=event.width)
        self._stretch_body()
        self._sync_bar()

    def _sync_bar(self):
        shown = bool(self._bar.winfo_manager())
        if self._needs_bar() and not shown:
            self._bar.pack(side=tk.RIGHT, fill=tk.Y, padx=(self._bar_gap, 0))
        elif not self._needs_bar() and shown:
            self._bar.pack_forget()
            self._canvas.yview_moveto(0)

    def _wheel(self, event):
        under = self.winfo_containing(event.x_root, event.y_root)
        if under is not None and isinstance(under.winfo_toplevel(), SelectList):
            return  # an open drop-down list takes the wheel
        if self._bar.winfo_manager() and under is not None and str(under).startswith(str(self)):
            if self._inner_scroll_takes(under):
                return  # a list inside this one (the Theme Editor's layers) scrolls instead of this frame
            self._canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _inner_scroll_takes(self, under):
        """True when `under` sits in another ScrollFrame, nested in this one, whose scroll bar is showing."""
        w = under
        while w is not None and w is not self:
            if isinstance(w, ScrollFrame) and w is not self and w._bar.winfo_manager():
                return True
            w = w.master
        return False
