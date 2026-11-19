"""Gallery card corner controls (v0.3.0): the organize and delete controls are bare icons (no box, no line, no background)
in the corners of the card, in a bar above the preview, never on the picture."""

import tkinter as tk
from pathlib import Path

from scripts.gui_design import PALETTE, mix

ICON = 22  # px: the icon's clickable square
MARGIN = 6  # px from the card's edge to the icon, top and sides
BAR = ICON + MARGIN  # height of the bar that holds the icons
MDL2 = Path("C:/Windows/Fonts/segmdl2.ttf")
BIN = "\ue74d"


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(MDL2), size)
    except OSError:
        return None


def icon_image(kind, colour):
    """RGBA ICON x ICON picture of "organize" (a long bar over a short one) or "delete" (a bin) in `colour`."""
    from PIL import Image, ImageColor, ImageDraw
    k = 4
    size = ICON * k
    glyph = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(glyph)
    if kind == "organize":
        w, h = 14 * k, 10 * k
        x0, y0 = (size - w) // 2, (size - h) // 2
        d.rounded_rectangle((x0, y0, x0 + w, y0 + 3 * k), radius=int(1.5 * k), fill=255)
        d.rounded_rectangle((x0, y0 + 7 * k, x0 + 9 * k, y0 + h), radius=int(1.5 * k), fill=255)
    else:
        font = _font(16 * k)
        if font is not None:
            d.text((size // 2, size // 2), BIN, font=font, fill=255, anchor="mm")
        else:  # no Segoe MDL2 Assets: a plain bin
            d.rounded_rectangle((6 * k, 8 * k, 16 * k, 18 * k), radius=k, fill=255)
            d.rectangle((5 * k, 5 * k, 17 * k, 7 * k), fill=255)
            d.rectangle((9 * k, 3 * k, 13 * k, 5 * k), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (size, size), ImageColor.getrgb(colour) + (255,)), mask=glyph)
    return out.resize((ICON, ICON), Image.LANCZOS)


def corner_icons(parent, bg, marks):
    """One bare icon (a Label over the card, no box) per mark: (corner "nw" or "ne", kind "organize" or "delete", command),
    at the card's top corners. They float above whatever the card holds, like a picture in front in a document.
    Returns the labels; they keep their images."""
    from PIL import ImageTk
    labels = []
    for corner, kind, command in marks:
        rest = mix(PALETTE["crit"], PALETTE["text"], 0.35) if kind == "delete" else PALETTE["text"]
        lit = PALETTE["crit"] if kind == "delete" else PALETTE["cyan"]
        pictures = {c: ImageTk.PhotoImage(icon_image(kind, c)) for c in (rest, lit)}
        label = tk.Label(parent, image=pictures[rest], bg=bg, bd=0, highlightthickness=0, cursor="hand2")
        label._images = list(pictures.values())
        label._kind = kind
        label.bind("<Enter>", lambda _e, w=label, p=pictures[lit]: w.configure(image=p))
        label.bind("<Leave>", lambda _e, w=label, p=pictures[rest]: w.configure(image=p))
        label.bind("<Button-1>", lambda _e, c=command: c())
        if corner == "nw":
            label.place(x=2 + MARGIN, y=2 + MARGIN, anchor="nw")
        else:
            label.place(relx=1.0, x=-(2 + MARGIN), y=2 + MARGIN, anchor="ne")
        labels.append(label)
    return labels
