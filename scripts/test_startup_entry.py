"""The Start-with-Windows entry starts the GUI hidden in the tray, never the console Monitor (v0.3.7.2)."""
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from scripts import startup_entry as se

GUI = r"C:\Program Files\TURMO Display Control\TURMO-Display-Control.exe"


class StartupEntry(unittest.TestCase):
    def test_command_runs_the_gui_with_startup(self):
        self.assertEqual(se.command(GUI), f'"{GUI}" --startup')

    def test_an_old_entry_is_upgraded_once(self):
        for old in (r'"C:\Program Files\TURMO Display Control\TURMO-Monitor.exe" --monitor',
                    r'"C:\Windows\System32\conhost.exe" --headless "C:\P\TURMO-Monitor.exe" --monitor'):
            new = se.upgraded(old, GUI)
            self.assertEqual(new, se.command(GUI))
            self.assertIsNone(se.upgraded(new, GUI))

    def test_a_foreign_or_odd_value_is_left_alone(self):
        for v in (r'"C:\Other\thing.exe" --x', "", None, 5):
            self.assertIsNone(se.upgraded(v, GUI))

    def test_the_installer_writes_the_same_form(self):
        iss = open(os.path.join(ROOT, "installer", "turmo.iss"), encoding="utf-8").read()
        self.assertIn('""{app}\\TURMO-Display-Control.exe"" --startup', iss)
        self.assertNotIn("conhost", iss.split("[Registry]")[1].split("[Run]")[0])

    def test_the_app_starts_hidden_and_without_a_splash(self):
        src = open(os.path.join(ROOT, "scripts", "turmo_app_enhanced.py"), encoding="utf-8").read()
        self.assertIn('STARTUP = "--startup" in sys.argv', src)
        self.assertIn("if not STARTUP:", src)


if __name__ == "__main__":
    unittest.main()
