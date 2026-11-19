"""In-app dialog: a dimmed layer over the window with a rounded card in the middle (replaces Tk's Toplevel
dialogs, which are drawn by Windows in the wrong colours). Built from the app's own controls. Escape, the
close button or a click outside the card closes it."""

import tkinter as tk

from scripts.gui_design import ICON_FONT, PALETTE, mix
from scripts.gui_widgets import RoundedCard, Stepper, make_button

ICON_CLOSE = ""  # Segoe MDL2 Assets: Cancel


class Modal:
    def __init__(self, app, title, width=420, dismissable=True):
        old = getattr(app, "_modal", None)
        if old is not None:
            old.close()
        self.app, bg2 = app, PALETTE["bg2"]
        scrim_colour = mix(PALETTE["bg0"], "#000000", 0.5)
        self.scrim = tk.Frame(app.root, bg=scrim_colour)
        self.scrim.place(x=0, y=0, relwidth=1, relheight=1)
        self.card = RoundedCard(self.scrim, bg2, PALETTE["line2"], scrim_colour, radius=16, width=width)
        head = tk.Frame(self.card.inner, bg=bg2)
        head.pack(fill=tk.X, padx=20, pady=(16, 4))
        tk.Label(head, text=title, bg=bg2, fg=PALETTE["text"], font=(app.ui_semibold, 13)).pack(side=tk.LEFT)
        if dismissable:  # a dialog that must be answered (the first-run one) has no cross, no Escape, no click outside
            make_button(head, ICON_CLOSE, self.close, (ICON_FONT, 10), variant="ghost", backdrop=bg2, small=True,
                        padx=8).pack(side=tk.RIGHT)
        self.body = tk.Frame(self.card.inner, bg=bg2)
        self.body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(8, 18))
        self._esc = None
        if dismissable:
            self.scrim.bind("<Button-1>", lambda _e: self.close())
            self._esc = app.root.bind("<Escape>", lambda _e: self.close(), add="+")  # a field in the card has the focus, not the scrim
        app._modal = self
        tk.Misc.lift(self.scrim)

    def show(self):
        """Fit the card to its content, then slide it up into the middle."""
        card, scrim = self.card, self.scrim
        card._fit()
        scrim.update_idletasks()
        scrim.focus_force()

        def rise(step):
            if not card.winfo_exists():
                return
            t = step / 8
            card.place(relx=0.5, rely=0.5, y=round(24 * (1 - t) ** 2), anchor="center")
            if step < 8:
                scrim.after(15, rise, step + 1)
        rise(0)

    def close(self):
        if getattr(self, "_esc", None):
            try:
                self.app.root.unbind("<Escape>", self._esc)
            except tk.TclError:
                pass
            self._esc = None
        if self.scrim.winfo_exists():
            self.scrim.destroy()
        if getattr(self.app, "_modal", None) is self:
            self.app._modal = None


def form_label(parent, text, font, top=10):
    tk.Label(parent, text=text, bg=PALETTE["bg2"], fg=PALETTE["muted"], font=font, anchor="w").pack(
        fill=tk.X, pady=(top, 4))


def form_field(parent, build, **pack):
    """A rounded field (the dark fill of the design's inputs); `build(inner)` puts the Entry or Spinbox in it."""
    card = RoundedCard(parent, PALETTE["bg0"], PALETTE["line2"], PALETTE["bg2"], radius=10)
    card.pack(fill=tk.X, **pack)
    build(card.inner)
    card._fit()
    return card


def form_entry(parent, var, font):
    return form_field(parent, lambda inner: tk.Entry(
        inner, textvariable=var, bg=PALETTE["bg0"], fg=PALETTE["text"], insertbackground=PALETTE["text"],
        relief=tk.FLAT, highlightthickness=0, font=font, width=1).pack(fill=tk.X, padx=10, ipady=5))


def form_spin(parent, var, low, high, font):
    return form_field(parent, lambda inner: Stepper(inner, var, low, high, PALETTE["bg0"], font).pack(fill=tk.X))
