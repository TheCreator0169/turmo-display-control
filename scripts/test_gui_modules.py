"""Structure of the GUI modules (v0.2.3): the app was split into turmo_app_enhanced.py, gui_common.py and page modules.
A name that moved out of the app but was not imported back fails only when that code runs (DEFAULT_THEME did, in
gallery_delete), so every module is checked for names it uses and never defines or imports."""
import ast
import builtins
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

# The GUI's own modules: the entry file, the shared environment, and the pages split out of it.
GUI_MODULES = ["turmo_app_enhanced.py", "gui_common.py", "theme_editor.py", "gallery_page.py",
               "diagnostics_page.py", "preview_page.py", "graph_page.py", "about_page.py"]
# Page modules call this size limit the point of the split.
APP_MAX_LINES = 3000


def bound_names(tree):
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, ast.arg):
            names.add(n.arg)
        elif isinstance(n, ast.Import):
            names.update((a.asname or a.name.split(".")[0]) for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            names.update((a.asname or a.name) for a in n.names if a.name != "*")
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            names.update(n.names)
    return names


class ModulesDefineWhatTheyUse(unittest.TestCase):
    def test_no_undefined_names(self):
        import scripts.gui_common as common
        for name in GUI_MODULES:
            tree = ast.parse((HERE / name).read_text(encoding="utf-8"))
            star = any(isinstance(n, ast.ImportFrom) and n.module == "scripts.gui_common" and n.names[0].name == "*"
                       for n in tree.body)
            known = bound_names(tree) | set(dir(builtins)) | (set(common.__all__) if star else set())
            known |= {"__file__", "__name__", "__doc__"}
            used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
            self.assertEqual(sorted(used - known), [], f"{name} uses names it never defines or imports")

    def test_the_app_file_stays_small(self):
        lines = len((HERE / "turmo_app_enhanced.py").read_text(encoding="utf-8").splitlines())
        self.assertLess(lines, APP_MAX_LINES, "turmo_app_enhanced.py grew back: put new pages in their own module")


class SwallowedErrors(unittest.TestCase):
    """v0.2.3: an `except ...: pass` hid the frozen ImageEnhance bug. A handler that does nothing must log through
    log_swallowed(), or say why on its `pass` line with `# ok:`."""

    def test_every_silent_handler_logs_or_explains_itself(self):
        silent = []
        for name in GUI_MODULES:
            src = (HERE / name).read_text(encoding="utf-8")
            lines = src.splitlines()
            for n in ast.walk(ast.parse(src)):
                # silent = the handler neither calls anything (log, message, dialog) nor re-raises: it only passes,
                # continues, returns or assigns a default
                if isinstance(n, ast.ExceptHandler) and not any(
                        isinstance(x, (ast.Call, ast.Raise)) for b in n.body for x in ast.walk(b)):
                    text = " ".join(lines[n.lineno - 1:n.end_lineno])
                    if "# ok:" not in text:
                        silent.append(f"{name}:{n.lineno}")
        self.assertEqual(silent, [], "silent except handlers: log them with log_swallowed() or add '# ok: why'")

    def test_log_swallowed_writes_once_per_place_and_never_raises(self):
        from unittest import mock
        import scripts.gui_common as common
        common._swallowed_seen.clear()
        with mock.patch.object(common, "log_runtime") as log:
            common.log_swallowed("here", ValueError("x"))
            common.log_swallowed("here", ValueError("y"))
            common.log_swallowed("there", ValueError("z"))
        self.assertEqual(log.call_count, 2)
        self.assertIn("SWALLOWED", log.call_args_list[0].args)
        with mock.patch.object(common, "log_runtime", side_effect=OSError("disk full")):
            common.log_swallowed("again", KeyError("k"))  # must not raise


class LanguageTable(unittest.TestCase):
    """v0.2.7: every text the window draws through tr() has a French and a Portuguese entry."""

    def test_every_text_drawn_through_tr_is_in_the_table_for_every_language(self):
        from scripts import i18n
        used = {}
        for path in sorted(HERE.glob("*.py")):
            if path.name.startswith("test_"):
                continue
            for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr":
                    if n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                        used.setdefault(n.args[0].value, path.name)
        self.assertGreater(len(used), 150, "the scan found too few tr() texts: has the call form changed?")
        for text, where in used.items():
            self.assertIn(text, i18n.TABLE, f"{where}: tr({text!r}) has no entry in i18n.TABLE")
        for text, entry in i18n.TABLE.items():
            self.assertEqual(len(entry), len(i18n.LANGUAGES) - 1, f"{text!r} lacks a language")
            for language, written in zip(i18n.LANGUAGES[1:], entry):
                self.assertTrue(written.strip(), f"{text!r} has no {language} text")
            self.assertEqual(text.count("\n"), entry[0].count("\n"), f"{text!r}: line breaks differ in French")
            self.assertEqual(text.count("\n"), entry[1].count("\n"), f"{text!r}: line breaks differ in Portuguese")

    def test_no_function_uses_tr_as_a_local_name(self):
        """A local named tr (the Theme Editor had `tr = tk.Frame(...)`, a table row) makes every tr(...) call in that
        function raise UnboundLocalError, in English too: it broke widget selection and nothing else noticed."""
        for path in sorted(HERE.glob("*.py")):
            if path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    bound = {a.arg for a in n.args.args + n.args.kwonlyargs}
                    bound |= {t.id for t in ast.walk(n) if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)}
                    self.assertNotIn("tr", bound, f"{path.name}:{n.lineno} {n.name} binds the name tr")

    def test_the_names_the_window_looks_up_are_translated_where_they_are_drawn(self):
        """The sidebar, the group labels and the Dashboard card titles are drawn with tr(name) from constants."""
        from scripts import i18n
        from scripts import gui_design as gd
        from scripts.gui_common import DASHBOARD_METRICS, DASHBOARD_METRICS_2
        names = list(gd.SIDEBAR_ITEMS) + [g for g, _ in gd.SIDEBAR_GROUPS] + [m[1] for m in DASHBOARD_METRICS + DASHBOARD_METRICS_2]
        # drawn with tr(variable): the graph table's columns, the Settings page list, the Dashboard rows
        names += ["ID", "Sensor", "Min", "Max", "Color", "Fill", "History", "Smooth",
                  "Windows startup", "CPU temperature", "Display", "Language", "Units", "Visible widgets", "Appearance", "Temperature", "Clock", "Data", "Version", "Settings file", "Landscape", "Portrait",
                  "Port", "Screen colour", "Colour correction", "Red", "Green", "Blue", "Reset colours", "Reset", "Backup & restore", "TURMO port", "Resolution", "Active theme", "Status"]
        # drawn with tr(variable) too: gallery categories, sensor names, the Diagnostics rows and buttons, the editor palette
        names += list(gd.GALLERY_CATEGORIES) + list(gd.SENSOR_NAMES.values()) + [
            "Connection", "Frames", "Serial latency", "App CPU", "GUI", "Monitor worker", "Live Preview", "Tray",
            "Restart Monitor", "Export logs", "Flush buffer", "Hardware reset", "Rect", "Clock", "Metric", "Gauge", "Bar",
            "Graph", "Text", "Icon", "Card or fill", "Time and date", "Number + unit", "Value ring", "Progress bar",
            "Sensor history", "Static label", "Round icon", "Monitor running", "COM port busy", "No device",
            "Connected", "Busy", "Disconnected", "Running", "Stopped", "CPU", "GPU", "RAM", "Network", "Disk"]
        for name in names:
            self.assertIn(name, i18n.TABLE, name)

    def test_the_official_theme_descriptions_and_the_about_features_are_translated(self):
        import json
        from scripts import i18n
        for path in sorted((HERE.parent / "themes").glob("*/theme.json")):
            text = json.loads(path.read_text(encoding="utf-8")).get("description", "")
            if text:
                self.assertIn(text, i18n.TABLE, f"{path.parent.name}: description has no translation")
        source = (HERE / "about_page.py").read_text(encoding="utf-8")
        start = source.index("features = [")
        features = ast.literal_eval(source[start + len("features = "):source.index("]", start) + 1])
        for text in features:
            self.assertIn(text, i18n.TABLE, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
