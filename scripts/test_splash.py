"""Tests for the loading screen (scripts/splash.py, v0.2.1): timeline, loaded-share milestones, frame files,
centring, transparency, and a smoke run of the splash thread."""
import json
import sys
import time
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import splash  # noqa: E402


class TimelineTests(unittest.TestCase):
    def test_t_alone_then_wordmark(self):
        self.assertEqual(splash.frame_index(0), 0)
        self.assertEqual(splash.frame_index(splash.LEAD_IN), 0)
        self.assertEqual(splash.frame_index(splash.LEAD_IN + splash.REVEAL), splash.FRAMES - 1)
        self.assertEqual(splash.frame_index(60), splash.FRAMES - 1)  # held, never loops back

    def test_frames_never_go_backwards(self):
        seq = [splash.frame_index(t / 100) for t in range(0, 400)]
        self.assertEqual(seq, sorted(seq))


class LoadedShareTests(unittest.TestCase):
    def test_steps_are_unique_and_end_at_one(self):
        names = [n for n, _ in splash.STEPS]
        self.assertEqual(len(names), len(set(names)))
        self.assertAlmostEqual(splash.step_target(set(names)), 1.0)
        self.assertEqual(splash.step_target(set()), 0.0)

    def test_progress_follows_milestones_not_the_clock(self):
        a = splash.step_target({"imports"})
        b = splash.step_target({"imports", "settings", "cleanup"})
        self.assertTrue(0 < a < b < 1)

    def test_app_calls_only_known_milestones(self):
        import re
        src = (Path(__file__).resolve().parent / "turmo_app_enhanced.py").read_text(encoding="utf-8")
        used = set(re.findall(r'_splash_step\("(\w+)"\)', src))
        self.assertEqual(used, {n for n, _ in splash.STEPS})

    def test_mask_offset_moves_the_loaded_edge_across_the_logo(self):
        ink = [60, 339]
        w = splash.SIZE[0]
        none, half, full = (splash.mask_offset(v, ink) for v in (0.0, 0.5, 1.0))
        self.assertGreater(none, half)
        self.assertGreater(half, full)
        self.assertEqual(w - full, ink[1])                      # all the ink is loaded
        self.assertEqual(w - none, ink[0] - splash.FILL_SOFT)   # nothing is, soft edge included
        self.assertLessEqual(none + w, 2 * w + splash.FILL_SOFT)  # crop stays inside the ramp


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.folder = splash.asset_dir()
        self.meta = json.loads((self.folder / "loading_meta.json").read_text(encoding="utf-8"))

    def test_every_frame_and_ghost_exists_and_nothing_stale(self):
        for i in range(splash.FRAMES):
            for prefix in ("loading", "loading_ghost"):
                self.assertTrue((self.folder / f"{prefix}_{i:02d}.png").is_file(), (prefix, i))
        self.assertEqual(len(list(self.folder.glob("loading_*.png"))), 2 * splash.FRAMES)
        self.assertEqual((self.meta["size"], self.meta["frames"]), (list(splash.SIZE), splash.FRAMES))

    def test_reveal_is_at_least_30_distinct_frames_per_second(self):
        self.assertGreaterEqual((splash.FRAMES - 1) / splash.REVEAL, 30)

    def test_frames_are_transparent_with_no_background(self):
        from PIL import Image
        im = Image.open(self.folder / f"loading_{splash.FRAMES - 1:02d}.png")
        self.assertEqual((im.mode, im.size), ("RGBA", splash.SIZE))
        for corner in ((0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1)):
            self.assertEqual(im.getpixel(corner)[3], 0, corner)

    def test_full_wordmark_is_centred_in_the_box(self):
        from PIL import Image
        im = Image.open(self.folder / f"loading_{splash.FRAMES - 1:02d}.png")
        x0, y0, x1, y1 = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
        self.assertLessEqual(abs((x0 + x1) / 2 - im.width / 2), 1)
        self.assertLessEqual(abs((y0 + y1) / 2 - im.height / 2), 1)
        self.assertEqual([x0, x1], self.meta["ink_x"])  # the fill maps onto exactly this width

    def test_ghost_is_the_same_logo_with_the_colours_swapped(self):
        from PIL import Image, ImageChops
        full = Image.open(self.folder / "loading_48.png")
        ghost = Image.open(self.folder / "loading_ghost_48.png")
        self.assertEqual(ImageChops.difference(full.getchannel("A"), ghost.getchannel("A")).getbbox(), None)  # same silhouette

        def luminance(im, box):
            px = [im.getpixel((x, y)) for x in range(box[0], box[2]) for y in range(box[1], box[3])]
            opaque = [p for p in px if p[3] == 255]
            return sum(sum(p[:3]) / 3 for p in opaque) / len(opaque)
        x0, y0, x1, y1 = full.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
        t_face = (x0 + 25, y0 + 8, x0 + 55, y0 + 18)   # inside the top bar of the T
        self.assertGreater(luminance(full, t_face), 200)    # loaded: white in front
        self.assertLess(luminance(ghost, t_face), 55)       # not loaded: black in front


class ThreadSmoke(unittest.TestCase):
    def test_splash_runs_at_30_fps_and_closes(self):
        s = splash.Splash()
        self.assertTrue(s.start())
        for name, _ in splash.STEPS:
            s.step(name)
            time.sleep(0.05)
        time.sleep(0.3)
        s.finish()
        self.assertFalse(s.thread.is_alive())
        n, span, fps, gap = s.stats()
        self.assertGreater(s.target, 0.99)
        self.assertGreaterEqual(fps, 30, (n, span, fps, gap))
        self.assertLess(gap, 100, (n, span, fps, gap))

    def test_splash_thread_does_not_become_the_default_root(self):
        s = splash.Splash()
        self.assertTrue(s.start())
        try:
            self.assertIsNone(tk._default_root)
        finally:
            s.finish()


if __name__ == "__main__":
    unittest.main()
