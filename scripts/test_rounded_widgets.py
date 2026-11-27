#!/usr/bin/env python3
"""RoundedCard and RoundedButton tests on a real Tk root (skipped when no display is available).

Run:  .venv-win\\Scripts\\python.exe scripts\\test_rounded_widgets.py
"""
import os
import sys
import tkinter as tk
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import turmo_app_enhanced as app  # noqa: E402
from scripts import gui_widgets as gw  # noqa: E402

FONT = ("Segoe UI", 10)


class RoundedWidgetTests(unittest.TestCase):
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

    def _button(self, **kw):
        calls = []
        btn = app.RoundedButton(self.root, "Go", lambda: calls.append(1), "#000000", "#111111",
                                "#ffffff", "#222222", FONT, **kw)
        btn.pack()
        self.root.update()
        return btn, calls

    def _click(self, btn, x=3, y=3):
        btn.event_generate("<ButtonRelease-1>", x=x, y=y)
        self.root.update()

    def test_click_calls_command_once(self):
        btn, calls = self._button()
        self._click(btn)
        self.assertEqual(calls, [1])

    def test_release_outside_does_not_call(self):
        btn, calls = self._button()
        self._click(btn, x=-5, y=-5)
        self.assertEqual(calls, [])

    def test_disabled_ignores_click_and_state_round_trips(self):
        btn, calls = self._button()
        btn.config(state="disabled")
        self.assertEqual(btn.cget("state"), "disabled")
        self._click(btn)
        self.assertEqual(calls, [])
        btn.configure(state="normal")
        self.assertEqual(btn.cget("state"), "normal")
        self._click(btn)
        self.assertEqual(calls, [1])

    def test_state_copied_from_a_tk_button_works(self):
        # the dashboard copies cget("state") of the Monitor tab's buttons; Tk may hand back a Tcl object
        source = tk.Button(self.root, state="normal")
        btn, calls = self._button()
        btn.config(state=source.cget("state"))
        self._click(btn)
        self.assertEqual(calls, [1])
        source.config(state="disabled")
        btn.config(state=source.cget("state"))
        self._click(btn)
        self.assertEqual(calls, [1])

    def test_bg_fg_text_change_redraws(self):
        btn, _ = self._button(radius=None)
        btn.config(bg="#abcdef", fg="#fedcba", text="Changed")
        self.root.update()
        self.assertEqual(btn.itemcget("bg", "fill"), "#abcdef")
        self.assertEqual(btn.itemcget("label", "fill"), "#fedcba")
        self.assertEqual(btn.itemcget("label", "text"), "Changed")

    def test_two_line_button_is_taller_than_one_line(self):
        one, _ = self._button()
        two = app.RoundedButton(self.root, "A\nB", None, "#000000", "#111111", "#fff", "#222", FONT)
        two.pack()
        self.root.update()
        self.assertGreater(two.winfo_height(), one.winfo_height())

    def test_card_grows_to_its_content(self):
        card = app.RoundedCard(self.root, "#111111", "#333333", "#000000")
        card.pack(fill=tk.X)
        for i in range(3):
            tk.Label(card.inner, text=f"row {i}", bg="#111111").pack()
        for _ in range(5):
            self.root.update()
        pad = 2 * card._inset
        self.assertGreaterEqual(card.winfo_height(), card.inner.winfo_reqheight() + pad)
        self.assertGreater(card.winfo_height(), 20)  # the 1 px start size would be a regression


class KitTests(unittest.TestCase):
    """The v0.2.0 kit in gui_widgets: Segmented, Switch, Slider, Select, buttons, rows, sidebar parts."""

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

    def _show(self, widget, **pack):
        widget.pack(**pack)
        for _ in range(3):
            self.root.update()
        return widget

    def _click(self, widget, x, y=5):
        widget.event_generate("<ButtonRelease-1>", x=x, y=y)
        self.root.update()

    def test_tip_shows_on_hover_follows_the_text_and_hides(self):
        """v0.2.6.1: the tooltip opens after the delay, closes on leave, and closes by itself when its text empties."""
        text = ["why there is a dash"]
        label = self._show(tk.Label(self.root, text="x"))
        tip = gw.Tip(label, lambda: text[0])
        tip.DELAY, tip.RECHECK = 10, 10

        def pump(ms):
            for _ in range(ms // 10):
                self.root.update()
                self.root.after(10)

        def open_tips():
            return [w for w in label.winfo_children() if isinstance(w, tk.Toplevel)]
        label.event_generate("<Enter>")
        pump(150)
        self.assertEqual(len(open_tips()), 1)
        text[0] = ""  # the value arrived while the pointer stayed on the label
        pump(150)
        self.assertEqual(open_tips(), [])
        text[0] = "again"
        label.event_generate("<Enter>")
        pump(150)
        self.assertEqual(len(open_tips()), 1)
        label.event_generate("<Leave>")
        self.root.update()
        self.assertEqual(open_tips(), [])
        text[0] = ""  # no text: no tooltip at all
        label.event_generate("<Enter>")
        pump(150)
        self.assertEqual(open_tips(), [])
        label.destroy()

    def test_button_variants_have_the_design_colours(self):
        for variant in ("default", "primary", "danger", "ghost"):
            style = gw.button_style(variant, "#0B0E14")
            self.assertEqual(len(style["disabled"]), 3, variant)
        self.assertEqual(gw.button_style("primary", "#0B0E14")["bg"], gw.PALETTE["cyan"])
        self.assertEqual(gw.button_style("primary", "#0B0E14")["fg"], gw.PALETTE["on_accent"])
        self.assertEqual(gw.button_style("danger", "#0B0E14")["fg"], gw.PALETTE["crit"])
        self.assertIsNone(gw.button_style("ghost", "#0B0E14")["outline"])
        with self.assertRaises(ValueError):
            gw.button_style("loud", "#0B0E14")

    def test_make_button_click_and_disabled_look(self):
        calls = []
        btn = self._show(gw.make_button(self.root, "Save", lambda: calls.append(1), FONT, variant="primary"))
        self._click(btn, 5)
        btn.config(state="disabled")
        self.assertEqual(btn.itemcget("label", "fill"), gw.button_style("primary", "#0B0E14")["disabled"][1])
        self._click(btn, 5)
        self.assertEqual(calls, [1])

    def test_segmented_picks_by_position_and_keeps_the_variable(self):
        var = tk.StringVar(value="a")
        picked = []
        seg = self._show(gw.Segmented(self.root, [("a", "One"), ("b", "Two"), ("c", "Three")], "a",
                                      picked.append, "#0B0E14", FONT, variable=var))
        first, second, third = seg._spans
        self._click(seg, (second[0] + second[1]) // 2)
        self.assertEqual((seg.get(), var.get(), picked), ("b", "b", ["b"]))
        var.set("c")  # a change made elsewhere moves the selection without calling the command
        self.assertEqual((seg.get(), picked), ("c", ["b"]))
        self._click(seg, 0)  # the tray padding is not a segment
        self.assertEqual(seg.get(), "c")

    def test_switch_toggles_and_follows_its_variable(self):
        var = tk.BooleanVar(value=False)
        seen = []
        sw = self._show(gw.Switch(self.root, False, seen.append, "#0B0E14", variable=var))
        self._click(sw, 10, 10)
        self.assertEqual((sw.get(), var.get(), seen), (True, True, [True]))
        var.set(False)
        self.assertFalse(sw.get())
        self._click(sw, 100, 10)  # outside the 42 px track
        self.assertEqual(seen, [True])

    def test_slider_value_from_position_steps_and_clamps(self):
        var = tk.IntVar(value=0)
        values = []
        sl = self._show(gw.Slider(self.root, 0, 100, 0, values.append, "#0B0E14", variable=var, step=5, width=224))
        w = sl.winfo_width()
        sl.event_generate("<Button-1>", x=w // 2, y=10)
        self.root.update()
        self.assertEqual(var.get() % 5, 0)
        self.assertTrue(45 <= var.get() <= 55)
        sl.event_generate("<Button-1>", x=w + 50, y=10)
        self.assertEqual(var.get(), 100)
        sl.event_generate("<Button-1>", x=-50, y=10)
        self.assertEqual(var.get(), 0)
        self.assertEqual(values[-1], 0)
        var.set(70)
        self.assertEqual(sl.get(), 70)

    def test_select_pick_updates_value_variable_and_command(self):
        var = tk.StringVar(value="COM3")
        picked = []
        sel = self._show(gw.Select(self.root, ["COM3", "COM4"], "COM3", picked.append, "#0B0E14", FONT,
                                   variable=var))
        sel._pick("COM4")
        self.assertEqual((sel.get(), var.get(), picked), ("COM4", "COM4", ["COM4"]))
        var.set("COM3")
        self.assertEqual(sel.get(), "COM3")

    def test_select_list_follows_a_growing_list_and_opens_as_wide_as_the_field(self):
        themes = ["a", "b"]
        sel = self._show(gw.Select(self.root, lambda: themes, "a", lambda v: None, "#0B0E14", FONT, width=220))
        themes.append("c")  # a theme was saved after the field was built
        self.assertEqual(sel.values(), ["a", "b", "c"])
        popup = gw.SelectList(sel, sel.values(), "b", sel._pick, FONT, sel._closed)
        try:
            self.root.update()
            self.assertEqual(popup.winfo_width(), sel.winfo_width())
            themes.extend("defgh")
            popup.close()
            popup = gw.SelectList(sel, sel.values(), "a", sel._pick, FONT, sel._closed)
            self.assertEqual(int(popup._cv.cget("height")), gw.SelectList.MAX_ROWS * gw.SelectList.ROW + 2 * gw.SelectList.PAD)
            self.assertGreater(popup._total, popup._ht)  # longer than the window: it scrolls
        finally:
            popup.close()

    def test_stepper_steps_within_its_range_and_recovers_from_half_typed_text(self):
        var = tk.IntVar(value=5)
        st = self._show(gw.Stepper(self.root, var, 0, 7, "#0B0E14", FONT), fill=tk.X)
        st.step(1)
        st.step(1)
        st.step(1)
        self.assertEqual(var.get(), 7)  # stops at the top
        st.step(-20)
        self.assertEqual(var.get(), 0)  # and at the bottom
        st.entry.delete(0, tk.END)  # emptied while typing
        st.step(1)
        self.assertEqual(var.get(), 1)
        self.assertEqual([c for c in st._arrows.find_all() if st._arrows.type(c) == "line"].__len__(), 3)  # divider and two chevrons

    def test_segmented_stretch_follows_the_parent_width_in_equal_segments(self):
        seg = gw.Segmented(self.root, [("a", "A"), ("b", "Longer label")], "a", None, "#0B0E14", FONT)
        seg.stretch()
        self._show(seg, fill=tk.X)
        self.root.update()
        self.assertEqual(seg._widths[0], seg._widths[1])
        self.assertAlmostEqual(sum(seg._widths), seg.winfo_width() - 2 * seg._tray - 2, delta=1)

    def test_rounded_entry_ring_turns_cyan_on_focus(self):
        var = tk.StringVar(value="x")
        card, entry = gw.rounded_entry(self.root, var, "#0B0E14", FONT)
        self._show(card, fill=tk.X)
        entry.focus_force()
        entry.event_generate("<FocusIn>")
        self.assertEqual(card._border, gw.P["cyan"])
        entry.event_generate("<FocusOut>")
        self.assertEqual(card._border, gw.P["line"])

    def test_hard_corners_have_only_opaque_or_transparent_pixels(self):
        card = gw.RoundedCard(self.root, "#101820", "#38414E", "#010203", radius=16, hard=True)
        imgs = gw._corner_images(card, 16, "#101820", "#38414E", 1)
        for photo in imgs:
            self.assertTrue(photo.width() == 16 and photo.height() == 16)
        soft = gw.RoundedCard(self.root, "#101820", "#38414E", "#010203", radius=16)
        self.assertIsNot(gw._corner_images(soft, 16, "#101820", "#38414E", 1)[0], imgs[0])  # cached apart

    def test_nav_item_active_state_and_click(self):
        calls = []
        item = self._show(gw.NavItem(self.root, "", "Dashboard", lambda: calls.append(1), "#12161F",
                                     ("Segoe MDL2 Assets", 13), FONT), fill=tk.X)
        self.assertFalse(item.active)
        item.set_active(True)
        self.assertTrue(item.active)
        # the active row is tinted (13% accent over the sidebar colour) and has a cyan bar
        self.assertEqual(item.itemcget("bg", "fill"), "#142F3A")
        self.assertIn(gw.PALETTE["cyan"], [item.itemcget(i, "fill") for i in item.find_all()
                                          if item.type(i) == "polygon"])
        self._click(item, 20, 10)
        self.assertEqual(calls, [1])

    def test_device_chip_dot_and_text(self):
        chip = self._show(gw.DeviceChip(self.root, "#12161F", FONT + ("bold",), ("Consolas", 9)), fill=tk.X)
        chip.set_status("TURMO · COM4", "ok")
        self.assertEqual(chip._info.cget("text"), "TURMO · COM4")
        self.assertEqual(chip._dot.cget("fg"), gw.PALETTE["green"])
        chip.set_status("No device", "off")
        self.assertEqual(chip._dot.cget("fg"), gw.PALETTE["dim"])

    def test_solid_badge_is_filled_with_the_colour_and_dark_text(self):
        badge = self._show(gw.Badge(self.root, "#1A2029", FONT + ("bold",), solid=True))
        badge.set("ACTIVE", gw.PALETTE["cyan"])
        self.root.update()
        self.assertEqual(badge.itemcget("label", "fill"), gw.PALETTE["on_accent"])
        self.assertIn(gw.PALETTE["cyan"], [badge.itemcget(i, "fill") for i in badge.find_all() if badge.type(i) != "image"])

    def test_rounded_button_active_bg_can_change(self):
        btn = self._show(gw.make_button(self.root, "All", lambda: None, FONT, variant="ghost", backdrop="#1A2029"))
        btn.config(bg=gw.PALETTE["cyan"], active_bg=gw.PALETTE["cyan"])
        self.assertEqual(btn._active_bg, gw.PALETTE["cyan"])

    def test_search_query_hides_its_hint_until_the_user_types(self):
        entry = self._show(tk.Entry(self.root))
        query = app._SearchQuery(entry, "Search themes", "#fff", "#555")
        self.assertEqual(query.get(), "")  # the hint is not a query
        self.assertEqual(entry.get(), "Search themes")
        query._focus(True)
        entry.insert(0, "hud")
        self.assertEqual(query.get(), "hud")
        query._focus(False)  # leaving a filled box keeps the text
        self.assertEqual(query.get(), "hud")
        entry.delete(0, tk.END)
        query._focus(False)
        self.assertEqual(query.get(), "")

    def test_badge_sizes_to_its_text_and_recolours(self):
        badge = self._show(gw.Badge(self.root, "#1A2029", FONT + ("bold",)))
        badge.set("Connected", gw.PALETTE["green"])
        self.root.update()
        self.assertGreater(badge.winfo_width(), 40)
        self.assertEqual(badge.itemcget("label", "text"), "Connected")
        self.assertEqual(badge.itemcget("label", "fill"), gw.PALETTE["green"])
        badge.set("Busy", gw.PALETTE["warn"])
        self.assertEqual(badge.itemcget("label", "fill"), gw.PALETTE["warn"])

    def test_control_button_click_disabled_and_state(self):
        calls = []
        btn = self._show(gw.ControlButton(self.root, "\uE768", "Start", "Worker", lambda: calls.append(1),
                                          "#1A2029", gw.PALETTE["green"], ("Segoe MDL2 Assets", 14), FONT, FONT))
        self._click(btn, 10, 10)
        btn.config(state="disabled")
        self.assertEqual(btn.cget("state"), "disabled")
        self._click(btn, 10, 10)
        btn.config(state="normal")
        self._click(btn, 10, 10)
        self.assertEqual(calls, [1, 1])
        self.assertGreater(btn.winfo_reqheight(), 80)  # the design's .ctrl-btn is at least 80 px tall

    def test_widget_tile_click_runs_the_command(self):
        calls = []
        tile = self._show(gw.WidgetTile(self.root, "", "Rect", "Card or fill", lambda: calls.append(1),
                                        "#1A2029", "#1A2029", ("Segoe MDL2 Assets", 14), FONT, FONT), fill=tk.X)
        tile.configure(width=120)
        self.root.update()
        self._click(tile, 20, 20)
        self.assertEqual(calls, [1])

    def test_choice_tile_selected_is_darker_and_click_runs_the_command(self):
        calls = []
        tile = self._show(gw.ChoiceTile(self.root, "Default", False, lambda: calls.append(1), "#1A2029", FONT),
                          fill=tk.X)
        self.root.update()
        raised = tile.itemcget("bg", "fill")
        tile.set_selected(True)
        self.assertNotEqual(tile.itemcget("bg", "fill"), raised)
        self.assertTrue(any(tile.type(i) == "text" and tile.itemcget(i, "text") == "" for i in tile.find_all()))
        self._click(tile, 20, 20)
        self.assertEqual(calls, [1])

    def test_toast_slides_in_and_goes(self):
        tmp = app.TurmoApp.__new__(app.TurmoApp)
        tmp.root, tmp.ui_font, tmp._toast = self.root, "Segoe UI", None
        tmp.toast("Saved")
        card = tmp._toast
        for _ in range(20):
            self.root.update()
            self.root.after(15)
        self.assertTrue(card.winfo_ismapped())
        tmp._toast_leave(card)
        deadline = __import__("time").time() + 2
        while tmp._toast is not None and __import__("time").time() < deadline:
            self.root.update()
        self.assertIsNone(tmp._toast)

    def test_theme_chip_active_state_click_and_ellipsis(self):
        calls = []
        chip = self._show(gw.ThemeChip(self.root, "Hardware Dashboard", "#4da3ff", lambda: calls.append(1),
                                       "#1A2029", "#1A2029", FONT), fill=tk.X)
        chip.configure(width=120)
        self.root.update()
        self.assertFalse(chip.active)
        chip.set_active(True)
        self.assertEqual(chip.itemcget("bg", "fill"), gw.PALETTE["cyan"])  # the first "bg" item is the border
        self._click(chip, 20, 10)
        self.assertEqual(calls, [1])

    def test_scroll_frame_shows_its_bar_only_when_the_content_is_taller(self):
        sf = gw.ScrollFrame(self.root, "#0B0E14")
        sf.configure(width=300, height=100)
        sf.pack_propagate(False)
        self._show(sf)
        tk.Frame(sf.body, height=50, width=100).pack()
        for _ in range(3):
            self.root.update()
        self.assertEqual(sf._bar.winfo_manager(), "")
        tk.Frame(sf.body, height=400, width=100).pack()
        for _ in range(3):
            self.root.update()
        self.assertEqual(sf._bar.winfo_manager(), "pack")

    def test_a_scrolling_list_inside_a_scrolling_column_takes_the_wheel_while_its_bar_shows(self):
        """v0.3.8.2: the Theme Editor's left column scrolls and holds the layers list, which scrolls too. The wheel over
        the list must move the list only (not both); over the rest of the column it moves the column."""
        outer = gw.ScrollFrame(self.root, "#0B0E14")
        outer.configure(width=300, height=150)
        outer.pack_propagate(False)
        self._show(outer)
        tk.Frame(outer.body, height=120, width=100).pack()
        inner = gw.ScrollFrame(outer.body, "#0B0E14")
        inner._canvas.configure(width=1, height=60)
        inner.pack(fill=tk.X)
        row = tk.Frame(inner.body, height=300, width=100)
        row.pack()
        tk.Frame(outer.body, height=200, width=100).pack()
        for _ in range(4):
            self.root.update()
        self.assertEqual(outer._bar.winfo_manager(), "pack")
        self.assertEqual(inner._bar.winfo_manager(), "pack")
        self.assertTrue(outer._inner_scroll_takes(row))  # over the list: the list scrolls, the column does not
        self.assertFalse(outer._inner_scroll_takes(outer.body))  # over the rest: the column scrolls
        self.assertFalse(inner._inner_scroll_takes(row))  # the list itself is not "inside" another list
        inner._bar.pack_forget()  # a list that fits (no bar) lets the wheel through
        self.assertFalse(outer._inner_scroll_takes(row))

    def test_stat_row_and_page_header(self):
        row = self._show(gw.StatRow(self.root, "cpu.load", "#0B0E14", FONT, ("Consolas", 9)), fill=tk.X)
        row.set_value("42%")
        row.set_status(gw.PALETTE["green"])
        self.assertEqual(row._value.cget("text"), "42%")
        head = self._show(gw.page_header(self.root, "Title", "Subtitle", "#0B0E14", FONT, FONT), fill=tk.X)
        self.assertTrue(head.actions.winfo_exists())


class ModalTests(unittest.TestCase):
    """The in-app dialog (scripts/modal.py) that replaces Windows dialogs and message boxes."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as e:
            raise unittest.SkipTest(f"no display: {e}")
        cls.root.geometry("400x300+40+40")

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _app(self):
        from types import SimpleNamespace
        return SimpleNamespace(root=self.root, ui_font="Segoe UI", ui_semibold="Segoe UI Semibold", _modal=None)

    def test_a_new_dialog_replaces_the_open_one(self):
        from scripts.modal import Modal
        fake = self._app()
        first = Modal(fake, "One")
        second = Modal(fake, "Two")
        self.assertFalse(first.scrim.winfo_exists())
        self.assertIs(fake._modal, second)
        second.close()
        self.assertIsNone(fake._modal)

    def test_escape_closes_it(self):
        from scripts.modal import Modal
        fake = self._app()
        modal = Modal(fake, "Esc")
        modal.show()
        self.root.update()
        # A key event goes to the window that has the keyboard focus. On a busy PC Windows can grant the focus late
        # (this test failed once in about 24 runs under load), so ask for it again and retry for up to 3 s.
        import time
        end = time.monotonic() + 3.0
        while fake._modal is not None and time.monotonic() < end:
            modal.scrim.focus_force()
            self.root.update()
            modal.scrim.event_generate("<Escape>")
            self.root.update()
            time.sleep(0.05)
        self.assertIsNone(fake._modal)


if __name__ == "__main__":
    unittest.main()
