#!/usr/bin/env python3
"""v0.3.0: pictures for the user's own themes (theme_picture.py). Run: .venv-win/Scripts/python.exe scripts/test_theme_picture.py"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "vendor"))
sys.path.insert(0, str(ROOT / "scripts"))
os.chdir(ROOT)

from PIL import Image  # noqa: E402
from scripts import theme_picture as tp  # noqa: E402


class Pictures(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def copy(self, name, as_name=None):
        dst = self.tmp / (as_name or name)
        shutil.copytree(ROOT / "themes" / name, dst)
        return dst

    def test_needs_a_picture_when_missing_or_older_than_the_theme(self):
        folder = self.copy("minimal-dark")
        self.assertTrue(tp.needs_picture(folder))
        Image.new("RGB", (4, 4)).save(folder / "preview.png")
        t = (folder / "theme.json").stat().st_mtime
        os.utime(folder / "preview.png", (t + 5, t + 5))
        self.assertFalse(tp.needs_picture(folder))
        os.utime(folder / "theme.json", (t + 60, t + 60))  # edited after the picture
        self.assertTrue(tp.needs_picture(folder))
        self.assertFalse(tp.needs_picture(self.tmp / "no-such-theme"))

    def test_a_landscape_and_a_portrait_theme_are_drawn_at_their_size(self):
        for name, size in (("minimal-dark", (480, 320)), ("minimal-dark-320x480", (320, 480))):
            folder = self.copy(name)
            self.assertTrue(tp.render_picture(folder), name)
            with Image.open(folder / "preview.png") as im:
                self.assertEqual(im.size, size)
            self.assertFalse((folder / "preview.png.tmp").exists())

    def test_a_broken_theme_writes_nothing_and_does_not_raise(self):
        folder = self.copy("minimal-dark")
        (folder / "theme.json").write_text("{not json", encoding="utf-8")
        self.assertFalse(tp.render_picture(folder))
        self.assertFalse((folder / "preview.png").exists())

    def test_the_maker_draws_in_a_thread_reports_once_and_does_not_retry_a_failure(self):
        good, bad = self.copy("minimal-dark", "good"), self.copy("minimal-dark", "bad")
        (bad / "theme.json").write_text("{not json", encoding="utf-8")
        maker = tp.PictureMaker()
        self.assertTrue(maker.start([good, bad]))
        while maker.running():
            time.sleep(0.05)
        self.assertTrue(maker.poll())
        self.assertFalse(maker.poll())  # said once
        self.assertTrue((good / "preview.png").is_file())
        self.assertFalse(maker.start([good, bad]))  # good is current, bad was tried for this version of its file
        t = (bad / "theme.json").stat().st_mtime
        shutil.copy2(ROOT / "themes" / "minimal-dark" / "theme.json", bad / "theme.json")
        os.utime(bad / "theme.json", (t + 60, t + 60))  # fixed: tried again
        self.assertTrue(maker.start([good, bad]))
        while maker.running():
            time.sleep(0.05)
        self.assertTrue((bad / "preview.png").is_file())


class NoLoop(unittest.TestCase):
    def test_a_theme_dated_in_the_future_is_drawn_once_not_forever(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        folder = tmp / "future"
        shutil.copytree(ROOT / "themes" / "minimal-dark", folder)
        future = time.time() + 3600
        os.utime(folder / "theme.json", (future, future))
        maker = tp.PictureMaker()
        self.assertTrue(maker.start([folder]))
        while maker.running():
            time.sleep(0.05)
        self.assertTrue(maker.poll())
        self.assertTrue(tp.needs_picture(folder))  # the picture still reads older than the file...
        self.assertFalse(maker.start([folder]))  # ...but this version of the theme was drawn: no second run

    def test_the_reason_for_a_failure_is_reported(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "theme.json").write_text("{not json", encoding="utf-8")
        told = []
        self.assertFalse(tp.render_picture(tmp, lambda where, exc: told.append(where)))
        self.assertEqual(len(told), 1)


class CardMarks(unittest.TestCase):
    def test_the_icons_are_square_rgba_with_no_box(self):
        from scripts import card_marks as cm
        for kind in ("organize", "delete"):
            im = cm.icon_image(kind, "#ffffff")
            self.assertEqual((im.size, im.mode), ((cm.ICON, cm.ICON), "RGBA"))
            self.assertGreater(im.getchannel("A").getextrema()[1], 200)  # something is drawn
            self.assertEqual(im.getpixel((0, 0))[3], 0)  # the corner stays transparent: no box

    def test_the_icons_float_in_the_card_corners_and_a_click_runs_the_command(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        self.addCleanup(root.destroy)
        from scripts import card_marks as cm
        hits = []
        root.geometry("240x80")
        left, right = cm.corner_icons(root, "#111111", [("nw", "delete", lambda: hits.append("bin")),
                                                        ("ne", "organize", lambda: hits.append("org"))])
        root.update()
        self.assertEqual((left.winfo_x(), left.winfo_y()), (cm.MARGIN + 2, cm.MARGIN + 2))
        self.assertEqual(right.winfo_x() + right.winfo_width(), root.winfo_width() - cm.MARGIN - 2)  # follows the width
        self.assertEqual(hits, [])  # nothing runs by itself
        left.event_generate("<Button-1>")
        right.event_generate("<Button-1>")
        self.assertEqual(hits, ["bin", "org"])


class LayerOrder(unittest.TestCase):
    """v0.3.0 M5: the Theme Editor's layer list moves a widget one layer up or down (the drawing order)."""

    def editor(self, ids):
        from scripts.theme_editor import ThemeEditor
        ed = type("E", (), {})()
        ed.widgets = list(ids)
        ed.redraws = 0
        ed.redraw_canvas = lambda: setattr(ed, "redraws", ed.redraws + 1)
        ed.move_widget = lambda w, step: ThemeEditor.move_widget(ed, w, step)
        ed._mover = lambda w, step: ThemeEditor._mover(ed, w, step)
        return ed

    def test_up_swaps_with_the_widget_drawn_after_it_and_the_ends_cannot_move_further(self):
        ed = self.editor(["a", "b", "c"])  # "c" is drawn last, so it is the top layer
        ed._mover("a", 1)()
        self.assertEqual(ed.widgets, ["b", "a", "c"])
        self.assertEqual(ed.redraws, 1)
        ed._mover("a", -1)()
        self.assertEqual(ed.widgets, ["a", "b", "c"])
        self.assertIsNone(ed._mover("c", 1))  # the top layer cannot go up
        self.assertIsNone(ed._mover("a", -1))  # the bottom one cannot go down
        ed.move_widget("c", 1)  # a stale call at the end changes nothing
        self.assertEqual((ed.widgets, ed.redraws), (["a", "b", "c"], 2))

    def test_the_arrows_of_the_chosen_row_run_the_move_and_never_reselect(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        self.addCleanup(root.destroy)
        from scripts.gui_widgets import LayerRow
        log = []
        row = LayerRow(root, "", "n", "Clock", True, lambda: log.append("select"), "#000", "#000", ("Arial", 10),
                       ("Arial", 10), ("Arial", 8), movers=(lambda: log.append("up"), None))
        row.pack(fill=tk.X)
        root.geometry("240x80")
        root.update()
        w = row.winfo_width()
        for x in (LayerRow._arrow_x("up", w), LayerRow._arrow_x("down", w), 30):
            row.event_generate("<ButtonRelease-1>", x=int(x), y=19)
        self.assertEqual(log, ["up", "select"])  # down is not possible: nothing; the row body still selects
        plain = LayerRow(root, "", "n", "Clock", False, lambda: None, "#000", "#000", ("Arial", 10), ("Arial", 10),
                         ("Arial", 8), movers=(lambda: None, lambda: None))
        self.assertIsNone(plain._arrow_at(w - 14, 19))  # an unselected row has no arrows


class Wiring(unittest.TestCase):
    def test_the_gallery_asks_for_the_pictures_after_drawing_its_cards(self):
        text = (ROOT / "scripts" / "gallery_page.py").read_text(encoding="utf-8")
        self.assertIn("self._gallery_pictures(shown)", text)
        self.assertIn("maker.start(folders)", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
