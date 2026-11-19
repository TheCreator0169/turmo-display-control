#!/usr/bin/env python3
"""v0.2.8: keyboard use and window sizing. The Canvas widgets are Tab stops with a visible ring, Space and Return
click, the controls with their own keys answer arrows, Escape closes a dialog wherever the focus is, a page scrolls to
the control that gets the focus. Skipped without a display (the sizing tests are pure).

Run:  .venv-win\\Scripts\\python.exe scripts\\test_keyboard.py
"""
import os
import sys
import tkinter as tk
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from scripts import gui_widgets as gw  # noqa: E402
from scripts.gui_design import FULL_SIZE, window_size  # noqa: E402

FONT = ("Segoe UI", 10)


class WindowSizeTests(unittest.TestCase):
    def test_100_percent_is_the_design_size(self):
        self.assertEqual(window_size(FULL_SIZE, 96), FULL_SIZE)

    def test_grows_with_the_scaling(self):
        self.assertEqual(window_size(FULL_SIZE, 144), (1800, 1140))
        self.assertEqual(window_size((540, 560), 120), (675, 700))

    def test_never_beyond_the_work_area(self):  # a 1366x768 laptop with the taskbar: 1366x728 left
        self.assertEqual(window_size(FULL_SIZE, 144, (1366, 728)), (1350, 680))

    def test_a_small_screen_at_100_percent_still_fits(self):
        w, h = window_size(FULL_SIZE, 96, (1280, 720))
        self.assertLessEqual(w, 1280 - 16)
        self.assertLessEqual(h, 720 - 48)

    def test_below_96_dpi_does_not_shrink(self):
        self.assertEqual(window_size(FULL_SIZE, 72), FULL_SIZE)


class KeyboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as e:
            raise unittest.SkipTest(f"no display: {e}")
        cls.root.geometry("+40+40")

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        gw._keyboard[0] = False

    def _press(self, widget, key):
        widget.focus_force()
        self.root.update()
        widget.event_generate(key)
        self.root.update()

    def _tab_stop(self, widget):
        """What Tk asks the widget's -takefocus script when Tab looks for the next stop."""
        return int(self.root.tk.call(str(widget.cget("takefocus")), str(widget)))

    def _button(self, **kw):
        calls = []
        btn = gw.RoundedButton(self.root, "Go", lambda: calls.append(1), "#000000", "#111111", "#ffffff", "#222222",
                               FONT, **kw)
        btn.pack()
        self.root.update()
        return btn, calls

    # --- the common behaviour ---
    def test_space_and_return_click_a_button(self):
        btn, calls = self._button()
        self._press(btn, "<space>")
        self._press(btn, "<Return>")
        self.assertEqual(len(calls), 2)
        btn.destroy()

    def test_a_disabled_button_is_skipped_and_silent(self):
        btn, calls = self._button()
        btn.config(state="disabled")
        self.assertEqual(self._tab_stop(btn), 0)
        self._press(btn, "<space>")
        self.assertEqual(calls, [])
        btn.config(state="normal")
        self.assertEqual(self._tab_stop(btn), 1)
        btn.destroy()

    def test_tab_visits_the_buttons_in_order(self):
        a, _ = self._button()
        b, _ = self._button()
        a.focus_force()
        self.root.update()
        self.assertIs(self.root.nametowidget(self.root.tk.call("tk_focusNext", str(a))), b)
        a.destroy()
        b.destroy()

    def test_the_ring_shows_after_a_key_not_after_a_click(self):
        btn, _ = self._button()
        gw._keyboard[0] = False  # the last input was the mouse
        btn.focus_force()
        self.root.update()
        self.assertEqual(btn.find_withtag("ring"), ())
        gw._keyboard[0] = True  # a key was pressed (Tab): the ring is drawn on the next redraw
        btn._focus(True)
        self.assertGreaterEqual(len(btn.find_withtag("ring")), 4)  # four arcs and four sides
        btn._focus(False)
        self.assertEqual(btn.find_withtag("ring"), ())
        btn.destroy()

    def test_the_ring_survives_a_redraw(self):
        btn, _ = self._button()
        gw._keyboard[0] = True
        btn._focus(True)
        btn.config(text="Other")  # a state change redraws the label
        self.assertGreaterEqual(len(btn.find_withtag("ring")), 4)  # four arcs and four sides
        btn.destroy()

    def test_tab_turns_the_ring_on_and_space_keeps_it(self):
        sw = gw.Switch(self.root, False, lambda v: None, "#000000")
        btn, _ = self._button()
        sw.pack(before=btn)
        self.root.update()
        sw.focus_force()
        self.root.update()
        gw._keyboard[0] = False
        self.root.event_generate("<Tab>")
        self.root.update()
        self.assertTrue(gw._keyboard[0], "Tab did not count as keyboard use")
        sw.focus_force()
        self.root.update()
        sw.event_generate("<space>")
        self.root.update()
        self.assertGreaterEqual(len(sw.find_withtag("ring")), 4, "the ring vanished after Space")
        sw.destroy()
        btn.destroy()

    def test_a_switch_toggles_with_space(self):
        got = []
        sw = gw.Switch(self.root, False, got.append, "#000000")
        sw.pack()
        self.root.update()
        self._press(sw, "<space>")
        self.assertEqual(got, [True])
        sw.destroy()

    # --- controls with their own keys ---
    def test_segmented_arrows_stop_at_the_ends(self):
        got = []
        seg = gw.Segmented(self.root, ["a", "b", "c"], "a", got.append, "#000000", FONT)
        seg.pack()
        self.root.update()
        self._press(seg, "<Right>")
        self._press(seg, "<Right>")
        self._press(seg, "<Right>")
        self.assertEqual(got, ["b", "c"])
        self._press(seg, "<Left>")
        self.assertEqual(got, ["b", "c", "b"])
        seg.destroy()

    def test_slider_arrows_home_end(self):
        got = []
        sl = gw.Slider(self.root, 10, 100, 50, got.append, "#000000", step=5)
        sl.pack()
        self.root.update()
        self._press(sl, "<Right>")
        self._press(sl, "<Left>")
        self._press(sl, "<Left>")
        self.assertEqual(got, [55, 50, 45])
        self._press(sl, "<End>")
        self._press(sl, "<Home>")
        self.assertEqual(got[-2:], [100, 10])
        sl.destroy()

    def test_select_opens_with_down_picks_with_return_and_keeps_focus(self):
        got = []
        sel = gw.Select(self.root, ["one", "two", "three"], "one", got.append, "#000000", FONT)
        sel.pack()
        self.root.update()
        self._press(sel, "<Down>")
        lst = next(w for w in sel.winfo_children() if isinstance(w, gw.SelectList))
        lst.event_generate("<Down>")  # from nothing, Down starts at the chosen row ("one"), then moves to "two"
        lst.event_generate("<Down>")
        lst.event_generate("<Return>")
        self.root.update()
        self.assertEqual(got, ["three"])
        self.assertEqual(sel.get(), "three")
        self.assertFalse(lst.winfo_exists())
        self.assertIs(self.root.focus_get(), sel)
        sel.destroy()

    def test_select_list_escape_closes_without_picking(self):
        got = []
        sel = gw.Select(self.root, ["one", "two"], "one", got.append, "#000000", FONT)
        sel.pack()
        self.root.update()
        self._press(sel, "<Down>")
        lst = next(w for w in sel.winfo_children() if isinstance(w, gw.SelectList))
        lst.event_generate("<Escape>")
        self.root.update()
        self.assertFalse(lst.winfo_exists())
        self.assertEqual(got, [])
        sel.destroy()

    # --- dialogs and scrolling ---
    def test_escape_closes_a_dialog_while_a_field_has_the_focus(self):
        from scripts.modal import Modal
        fake = SimpleNamespace(root=self.root, ui_font="Segoe UI", ui_semibold="Segoe UI Semibold", _modal=None)
        modal = Modal(fake, "Esc")
        entry = tk.Entry(modal.body)
        entry.pack()
        modal.show()
        self.root.update()
        entry.focus_force()
        self.root.update()
        entry.event_generate("<Escape>")
        self.root.update()
        self.assertIsNone(fake._modal)
        self.assertFalse(modal.scrim.winfo_exists())

    def test_closing_a_dialog_removes_its_escape_binding(self):
        from scripts.modal import Modal
        fake = SimpleNamespace(root=self.root, ui_font="Segoe UI", ui_semibold="Segoe UI Semibold", _modal=None)
        before = self.root.bind("<Escape>")
        Modal(fake, "x").close()
        self.assertEqual(self.root.bind("<Escape>"), before)

    def test_a_page_scrolls_to_the_control_that_gets_the_focus(self):
        frame = tk.Frame(self.root, height=200, width=300)
        frame.pack_propagate(False)
        frame.pack()
        page = gw.ScrollFrame(frame, "#000000")
        page.pack(fill=tk.BOTH, expand=True)
        buttons = []
        for _ in range(30):
            b = gw.RoundedButton(page.body, "Go", lambda: None, "#000000", "#111111", "#ffffff", "#222222", FONT)
            b.pack()
            buttons.append(b)
        self.root.update()
        self.assertEqual(page._canvas.canvasy(0), 0)
        buttons[-1].focus_force()
        self.root.update()
        self.assertGreater(page._canvas.canvasy(0), 100)
        buttons[0].focus_force()
        self.root.update()
        self.assertEqual(page._canvas.canvasy(0), 0)
        frame.destroy()


if __name__ == "__main__":
    unittest.main()
