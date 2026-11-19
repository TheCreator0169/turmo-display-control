#!/usr/bin/env python3
"""Build assets/turmo_icon.png, the one TURMO logo, from design/v0.2.0/logo-t.webp.

The source is the white T with its black shadow on a transparent ground. This crops it, centres it on a
square and writes it at 1024 px; the window, taskbar and tray shrink that PNG themselves. No .ico is made.
It also writes design/v0.2.0/logo-white.png (the same picture, kept as the design asset).

Run:  .venv-win/Scripts/python.exe scripts/make_icon.py
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "design" / "v0.2.0" / "logo-t.webp"
DESIGN_COPY = ROOT / "design" / "v0.2.0" / "logo-white.png"
OUT = ROOT / "assets" / "turmo_icon.png"


def build():
    px = np.array(Image.open(SRC).convert("RGBA"))
    # the source has faint stray specks far from the T: keep only what is next to solid pixels
    near = Image.fromarray(((px[..., 3] >= 200) * 255).astype("uint8")).filter(ImageFilter.MaxFilter(5))
    px[..., 3] = np.where(np.array(near) > 0, px[..., 3], 0)
    im = Image.fromarray(px)
    im = im.crop(im.getbbox())
    side = max(im.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    square = square.resize((1024, 1024), Image.LANCZOS)
    OUT.parent.mkdir(exist_ok=True)
    square.save(OUT)
    square.save(DESIGN_COPY)
    return OUT


if __name__ == "__main__":
    print("wrote", build())
