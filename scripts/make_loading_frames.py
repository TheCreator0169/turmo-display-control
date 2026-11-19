"""Render the TURMO loading-screen frames (v0.2.1).

The T comes from design/v0.2.0/logo-t.webp (clean vector-like source); URMO is drawn with
Bahnschrift, sheared to the T's slant, with the same black extruded edge. Everything is drawn at 4x
and reduced with LANCZOS so edges are anti-aliased. There is no background: frames are transparent
(scripts/splash.py shows them in a per-pixel-alpha window). Two sets: the logo (white, black edge) and its
"ghost" (the same logo with the colours swapped: black face in front, white edge behind); the splash wipes the
logo over the ghost from left to right as loading progresses.

Usage: python scripts/make_loading_frames.py --write         (assets/loading_*.png and loading_meta.json)
       python scripts/make_loading_frames.py --sheet OUT_DIR  (preview on a dark and a light desktop)
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "design" / "v0.2.0" / "logo-t.webp"
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"

SIZE = (400, 240)          # splash window, 1x pixels (transparent: only the logo is seen)
SS = 4                     # supersampling
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RING = (150, 158, 170)     # 1 px outline: a white shape must read on a white desktop too

T_W = 172                  # T width, 1x (first look had 150; the logo is 15 % bigger without the bar)
URMO_X = 0.60              # URMO start, fraction of T width from T left
URMO_W = 1.15              # URMO span, fraction of T width
CAP_H = 0.28               # cap height, fraction of T height
MARGIN = 4                 # 1x px between the bottom of the T's bar (black edge and outline included) and the top of URMO
SHEAR = 0.26
EXTRUDE = 6                # black edge depth, 1x px (down-right)

FRAMES = 49                # frame 0 = T alone, last = full wordmark; 1.2 s of reveal = 40 distinct frames per second


def _outlined(im):
    """A 1 px grey outline round the shape."""
    grown = im.getchannel("A").filter(ImageFilter.MaxFilter(2 * SS + 1))
    ring = Image.new("RGBA", im.size, RING + (255,))
    ring.putalpha(grown)
    ring.alpha_composite(im)
    return ring


def _load_t():
    im = Image.open(LOGO).convert("RGBA")
    return im.crop(im.getchannel("A").getbbox())


def _urmo_layer(width, height, face, edge):
    """URMO, sheared, with extrusion, on a transparent layer of (width, height) at SS scale."""
    cap = int(height * CAP_H)
    font = ImageFont.truetype(FONT, int(cap / 0.72))
    try:
        font.set_variation_by_name("Bold")
    except Exception:
        pass
    letters = "URMO"
    boxes = [font.getbbox(c) for c in letters]
    glyph_w = sum(b[2] - b[0] for b in boxes)
    gap = cap * 0.14
    nat_w = glyph_w + gap * (len(letters) - 1)
    ext = EXTRUDE * SS
    pad = ext + 8
    lay_w = int(width + pad * 2 + cap * SHEAR)
    lay_h = int(cap + pad * 2)
    strip = Image.new("L", (int(nat_w) + 2, cap + 2), 0)
    d = ImageDraw.Draw(strip)
    x = 0
    cap_top = min(b[1] for b in boxes)
    for c, b in zip(letters, boxes):
        d.text((x - b[0], -cap_top), c, font=font, fill=255)
        x += (b[2] - b[0]) + gap
    # stretch wider (the wordmark is an extended face), then place on the padded layer
    strip = strip.resize((int(width), cap + 2), Image.LANCZOS)
    face_l = Image.new("L", (lay_w, lay_h), 0)
    face_l.paste(strip, (pad, pad))
    # shear to the right, keeping the baseline fixed
    face_l = face_l.transform(face_l.size, Image.AFFINE, (1, SHEAR, -SHEAR * (lay_h - pad), 0, 1, 0), Image.BICUBIC)
    edge_l = Image.new("L", face_l.size, 0)
    for i in range(1, ext + 1):
        edge_l.paste(255, (i, i), face_l)
    out = Image.new("RGBA", face_l.size, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", face_l.size, edge + (255,)), (0, 0), edge_l)
    out.paste(Image.new("RGBA", face_l.size, face + (255,)), (0, 0), face_l)
    return out, pad


def _bar_bottom(t, tw, th):
    """Row (SS scale, from the T's top) where the T's top bar, black edge included, ends over the columns URMO
    starts under: the end of the first opaque run in each of those columns."""
    alpha = t.getchannel("A")
    x_u = int(tw * URMO_X)
    bottom = 0
    for cx in range(x_u, min(tw - 1, x_u + int(tw * 0.3)), 4):
        y = 0
        while y < th and alpha.getpixel((cx, y)) < 128:
            y += 1
        if y == th:           # nothing opaque in this column (past the T's right end)
            continue
        while y < th and alpha.getpixel((cx, y)) >= 128:
            y += 1
        bottom = max(bottom, y)
    return bottom


def _ink_box(img):
    return img.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()


_OFF = None


def _offset():
    """(dx, dy) at SS scale that puts the full wordmark (T and URMO, edges included) in the middle of the window.
    Every frame uses it, so the T stays where it is while URMO slides out."""
    global _OFF
    if _OFF is None:
        x0, y0, x1, y1 = _ink_box(_compose(1.0, SIZE, (0, 0)))
        _OFF = ((SIZE[0] * SS - (x0 + x1)) // 2, (SIZE[1] * SS - (y0 + y1)) // 2)
    return _OFF


def render(progress, size=SIZE, inverted=False):
    """progress 0 = T alone, 1 = full TURMO. An RGBA image of `size`, the full wordmark centred in it.
    inverted: black face in front, white edge behind (the not-yet-loaded logo)."""
    big = _compose(progress, size, _offset(), inverted)
    return big.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def _compose(progress, size, off, inverted=False):
    w, h = size[0] * SS, size[1] * SS
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    t = _load_t()
    tw = T_W * SS
    th = round(t.height * tw / t.width)
    t = t.resize((tw, th), Image.LANCZOS)
    t0 = t
    if inverted:   # the source T is a white face with a black edge: swap them, keep the alpha
        r, g, b, a = t.split()
        t = Image.merge("RGBA", (ImageChops.invert(r), ImageChops.invert(g), ImageChops.invert(b), a))
    pad_t = 2 * SS
    t = _outlined(ImageOps.expand(t, pad_t, (0, 0, 0, 0)))
    total_w = tw * (URMO_X + URMO_W)
    left = int((w - total_w) / 2) + off[0]
    top = int((h - th) / 2) + off[1]
    uw = int(tw * URMO_W)
    layer, pad = _urmo_layer(uw, th, BLACK if inverted else WHITE, WHITE if inverted else BLACK)
    layer = _outlined(layer)
    ux = left + int(tw * URMO_X) - pad
    uy = top + _bar_bottom(t0, tw, th) + MARGIN * SS - pad   # URMO sits under the T's bar, a light margin below it
    # reveal: URMO slides out from behind the T
    reveal = max(0.0, min(1.0, progress))
    if reveal > 0:
        shift = int((1 - reveal) * uw * 0.12)   # letters slide out a little as the wipe moves right, U first
        part = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        part.paste(layer, (-shift, 0))
        mask = Image.new("L", layer.size, 0)
        edge_x = int(pad + uw * reveal + pad)
        ImageDraw.Draw(mask).rectangle((0, 0, edge_x, layer.height), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(SS * 3))
        a = part.getchannel("A")
        part.putalpha(Image.composite(a, Image.new("L", a.size, 0), mask))
        img.alpha_composite(part, (ux, uy))
    # T on top
    img.alpha_composite(t, (left - pad_t, top - pad_t))
    return img


def ease(x):
    return x * x * (3 - 2 * x)


def write_frames(out_dir):
    """assets/loading_<nn>.png (logo), loading_ghost_<nn>.png and loading_meta.json: the files scripts/splash.py
    loads (flat in assets/, so turmo.spec bundles them)."""
    out_dir = Path(out_dir)
    for i in range(FRAMES):
        full = render(ease(i / (FRAMES - 1)))
        full.save(out_dir / f"loading_{i:02d}.png", optimize=True)
        render(ease(i / (FRAMES - 1)), inverted=True).save(out_dir / f"loading_ghost_{i:02d}.png", optimize=True)
    x0, _y0, x1, _y1 = _ink_box(full)
    (out_dir / "loading_meta.json").write_text(
        json.dumps({"size": list(SIZE), "ink_x": [x0, x1], "frames": FRAMES}), encoding="utf-8")


def sheet(out_dir):
    """Preview: frames 0, 24, 48 at 0 %, 50 % and 100 % loaded, on a dark and a light desktop."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = json.loads((ROOT / "assets" / "loading_meta.json").read_text(encoding="utf-8"))
    x0, x1 = meta["ink_x"]
    sh = Image.new("RGB", (SIZE[0] * 3, SIZE[1] * 2))
    for r, desktop in enumerate(((20, 24, 32), (236, 238, 242))):
        for c, (idx, frac) in enumerate(((0, 0.0), (24, 0.5), (48, 1.0))):
            full = Image.open(ROOT / "assets" / f"loading_{idx:02d}.png")
            gh = Image.open(ROOT / "assets" / f"loading_ghost_{idx:02d}.png")
            mask = Image.new("L", full.size, 0)
            ImageDraw.Draw(mask).rectangle((0, 0, round(x0 + frac * (x1 - x0)), full.height), fill=255)
            bg = Image.new("RGBA", full.size, desktop + (255,))
            bg.alpha_composite(Image.composite(full, gh, mask))
            sh.paste(bg.convert("RGB"), (c * SIZE[0], r * SIZE[1]))
    sh.save(out_dir / "loading_sheet.png")


if __name__ == "__main__":
    if sys.argv[1] == "--write":
        write_frames(ROOT / "assets")
        print("frames written to assets/")
    elif sys.argv[1] == "--sheet":
        sheet(sys.argv[2])
        print("ok", sys.argv[2])
