"""Draws the installer's logo files from assets/turmo_icon.png (run again only when the logo changes; the outputs are committed):
turmo.ico (the Setup file's icon), wizard_side.bmp (164x314, welcome and finish pages), wizard_small.bmp (55x55, other pages)."""
import pathlib
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent
DARK = (11, 15, 20)  # the app's darkest surface (PALETTE bg0)
logo = Image.open(HERE.parent / "assets" / "turmo_icon.png").convert("RGBA")
logo = logo.crop(logo.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox())  # the T without its empty margin


def fitted(box, canvas, bg, pad):
    """The logo centred on a `box`-sized dark canvas with `pad` px around it."""
    img = Image.new("RGB", box, bg)
    k = min((box[0] - 2 * pad) / logo.width, (box[1] - 2 * pad) / logo.height)
    t = logo.resize((round(logo.width * k), round(logo.height * k)), Image.LANCZOS)
    img.paste(t, ((box[0] - t.width) // 2, (box[1] - t.height) // 2), t)
    return img


fitted((164, 314), None, DARK, 22).save(HERE / "wizard_side.bmp")
small = fitted((55, 55), None, DARK, 8)
small.save(HERE / "wizard_small.bmp")
square = Image.new("RGBA", (256, 256), DARK + (255,))
t = logo.resize((200, round(200 * logo.height / logo.width)), Image.LANCZOS)
square.paste(t, (28, (256 - t.height) // 2), t)
mask = Image.new("L", (256, 256), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, 255, 255), radius=44, fill=255)
square.putalpha(mask)
square.save(HERE / "turmo.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
