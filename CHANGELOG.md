TURMO - CHANGELOG
=================


v0.3.7.3 (2026-11-20)
----------------------
- Fix: if an old "Start with Windows" entry cannot be rewritten, the switch stays on (it showed off). The test run no longer reads or rewrites the real start-up entry.

v0.3.7.2 (2026-11-20)
----------------------
- "Start with Windows" now starts TURMO Display Control itself (`--startup`): no splash, the window stays hidden in the tray, and the GUI starts the Monitor with no console window. It replaces the v0.3.7.1 `conhost --headless` form. The installer writes the new entry; an older entry is rewritten when the app starts.

v0.3.7.1 (2026-11-20)
----------------------
- Fix: with "Start with Windows" on, a black console window opened at sign-in (the Monitor is a console program). The entry now runs it through `conhost.exe --headless`, so no window appears. The installer writes the new form; an entry written by an older version is rewritten when the app starts.

v0.3.7 (2026-11-20)
--------------------
- Installer: a page before the install explains the administrator rights (one scheduled task, "TURMO CpuTemp Helper", reads the CPU temperature only; the uninstaller removes it).
- The GitHub Actions build (started by hand) signs the Setup only when the SignPath secrets exist, so it can run unsigned until then.

v0.3.6.3 (2026-11-20)
---------------------
- Language / Dark-Light change: the picture of the old window now fades out (about 0.12 s) onto the new one instead of jumping to it. The redraw itself still takes about 1.5 s (Tk lays out about 1000 widgets).

v0.3.6.2 (2026-11-20)
---------------------
- Moving between pages: the old page stays on screen while the new one is drawn, then fades out (about 0.12 s), so cards no longer appear one after the other. Settings > Appearance > "Smooth page changes" (on by default; off: pages change at once). FR/PT texts are drafts.

v0.3.6.1 (2026-11-20)
---------------------
- Language / Dark-Light change: the window is redrawn in about 1.3 s instead of 3.8 s (old pages are dropped by Tk in one call; cards are sized before their page is shown).
- Moving between pages: the Theme Editor is built while the app is idle instead of when first opened (it filled in piece by piece for about 2 s; now about 0.5 s), and every page's cards have their size before the page is first shown.

v0.3.6 (2026-11-20)
-------------------
- Changing the language or the Dark/Light look no longer makes the window vanish: a picture of the window stays on screen while the pages are drawn again (still about 3 seconds, the window is frozen meanwhile).

v0.3.5 (2026-11-20)
-------------------
- Errors in plain words: no internet, timeout, busy server, file in use, disk full. The Update button says "No internet connection." offline. Import/export of settings, screenshot, log export and "Open folder" no longer fail silently.
- An error inside a button or timer is logged and shown once, instead of the button seeming dead.
- Settings: saved atomically; an imported file is checked first (old one kept as settings.json.bak); a damaged file is kept as settings.json.bad instead of being overwritten.
- Settings > Logs: "Write logs" switch (on by default). Off: no log file is written once the settings are read.
- About the texts: about 55 messages (status line, toasts, theme errors) are now translated. FR/PT are drafts.
- Welcome screen: a Language row (English / Français / Português) before Look; the choice applies at once and the screen reappears in that language. FR/PT "Four quick checks" is a draft.
- Clean-up: unused OrganizeButton removed.

v0.3.4 (2026-11-20)
-------------------
- About: the Update button now works. It asks GitHub for the latest release only when pressed; if a newer one exists it offers to download the installer, checks its SHA-256 against the release's SHA256SUMS.txt, then starts it. FR/PT texts are drafts.

v0.3.3 (2026-11-20)
-------------------
- Fix: the tray panel and the Minimalist window showed a dash for the GPU (and the CPU temperature) unless Live Preview was on; they now read the sensors like the Dashboard, also while the window is in the tray.
- Clean build: made from a neutral folder, so the compiled files no longer carry the builder's Windows user name or PC name. No change to the app.

v0.3.2 (2026-11-19)
-------------------
- About: a License row (GPL-3.0-or-later). FR/PT word "Licence" / "Licença" is a draft.

v0.3.1 (2026-11-19)
-------------------
- Licence: TURMO is GPL-3.0-or-later (was labelled MIT). LICENSE, README, THIRD_PARTY_NOTICES.md; the Setup shows the licence and installs both files.

v0.3.0 (2026-11-19)
-------------------
- Log regulator: old logs are removed (7 days and 20 MB by default, Settings > Logs, Clean now, Open folder); one rotating
  startup log.
- USB reconnect: the Monitor never exits on a USB error; it finds the display again by VID:PID 1A86:5722, with a 0.5, 1, 2, 5 s
  backoff and one log line per change. The app shows Connecting, Reconnecting or Not found (chip, Dashboard, Diagnostics,
  Minimalist view, tray tooltip) and a toast when the link is lost and back. Start works with no display plugged in.
- Installer (Inno Setup): copies the app, registers the CPU temperature task, optional start with Windows, upgrade keeps data,
  uninstall removes the task and asks before deleting settings. Proven in Windows Sandbox (install, upgrade, uninstall).
- First start: a welcome dialog (display, CPU temperature helper, Default or Minimalist look) that must be closed with Done.
- Switching Landscape or Portrait changes the display at once, without restarting the Monitor.
- Gallery: your own themes get a picture; the organize icon is on every card and the bin, pencil and copy icons on your own themes only.
- Theme Editor: the layer list moves a widget up or down in the drawing order.
- Version label 8 px on the portrait LCD themes; Serial latency tile in Diagnostics.
- Versions v0.2.2 to v0.2.9.x: development builds, not published.

v0.2.1 (2026-11-18)
-------------------
- Loading screen: the TURMO logo is the progress bar (transparent window, no background). The dark logo is
  wiped white from left to right as 16 real start-up steps complete. About 56 redraws per second measured on the frozen exe, with one short stall of about 170 ms.
- Main window stays hidden until it is fully drawn and the loading screen is gone (no flash, no half-drawn first frame).
- No terminal window at start (the .NET runtime check now runs hidden).
- First Monitor scan no longer freezes the window for about 5 s (one process snapshot).
- Known: the one-file exe unpacks for about 5 s before any splash can show.

v0.2.0 (validated 2026-11-18)
-------------------
- GUI redesign: Dashboard, sidebar, Minimalist view, light/dark window theme, tray quick panel, toasts, Language choice
  (saved, not translated yet), network rates in B/s to GB/s.

v0.1.0 notes (kept as written)
-----------------------------
v0.1.0 DEVELOPMENT (2026-11-14)
-------------------------------

NEW FEATURES:
- Complete GUI application (TURMO-Display-Control.exe) with tkinter
- Monitor worker (TURMO-Monitor.exe) for USB display communication
- 8 built-in themes: cyberpunk-neon, minimal-dark, futuristic-hud, matrix-terminal,
  rgb-gaming, hardware-dashboard, clean-white, custom-blank-canvas
- Theme alias "minimal" resolves to "minimal-dark"
- Theme Editor: drag-drop widget builder (8 widget types)
- Graph Configuration: add/edit/remove custom graphs
- Settings panel: 13 configurable fields with persistence
- Export/Import settings as JSON
- System tray integration (minimize, show, start/stop monitor, exit)
- Startup toggle (Windows Run registry)
- Centralized runtime logging with full traceback capture
- GPU telemetry via pynvml (NVIDIA)
- CPU telemetry via LibreHardwareMonitor (when service running)
- CPU telemetry via psutil (fallback)
- Single-instance mutex for both GUI and worker
- Exclusive COM4 ownership with automatic recovery
- CREATE_NO_WINDOW - no external CMD windows

FIXES:
- BUG-021: GPU telemetry - added pynvml, verified RTX 3050 detection
- BUG-024: Centralized runtime logging - created runtime_logging.py with
  excepthook, thread hook, safe_callback wrapper, worker output capture
- BUG-027: Theme name mismatch - added "minimal" alias in 4 code locations
- Fixed settings port default (COM5 -> COM4)
- Fixed LibreHardwareMonitor provider import in frozen EXE (pythonnet, clr hiddenimports)
- Fixed numpy/pillow in frozen EXE (hiddenimports, vendor bundle)
- Fixed theme directory naming (-320x480/-480x320 suffixes filtered)
- Fixed worker --check to use find_turmo_port() as fallback

VERIFIED:
- All worker CLI flags: --check, --test-image, --theme, --monitor, --high-quality,
  --landscape/--portrait, --gpu-index, --port, --once
- All 8 themes + minimal alias render correctly in frozen EXE
- All 11 GUI settings callbacks function correctly
- COM4 ownership: mutex blocks concurrent instances, releases on exit
- CPU Package temperature via LHM DLL: 53°C detected
- GPU temperature via pynvml: 60°C detected
- Centralized logging captures simulated COM errors, worker crashes, callback exceptions
- GUI launches without crash, initializes mutex, creates tray icon
- Settings persist to %APPDATA%/TURMO/settings.json
- No external CMD windows (CREATE_NO_WINDOW)

PARTIAL:
- Graph Config: settings fields work but toolbar menu item missing
- Theme Editor: fully functional but not tested via GUI button clicks
- Live Preview: pipeline verified in frozen mode, not via GUI button

UNVERIFIED (REQUIRES HARDWARE):
- Physical USB display (VID 1A86, PID 5722) visual confirmation
- LibreHardwareMonitor SERVICE integration (DLL works, service not running)
- Actual sensor data rendering on physical display

KNOWN ISSUES:
- test_gui_buttons.py test suite times out (tkinter mainloop deadlock in test harness)
- Portrait mode preview file permission warning (uses fallback, works)
- LHM service not running on test machine (GUI sensor path untested)

BUILD:
- turmo.spec: onefile, 40.2 MB, pythonnet+clr hiddenimports
- turmo_monitor.spec: onedir, 39.4 MB, pythonnet+clr+libre_panel hiddenimports
- Windows venv: .venv-win with pyinstaller, pillow, numpy, pyserial, psutil, tzdata, pystray, pynvml, pythonnet, libre_panel
- LibreHardwareMonitorLib.dll loaded from C:\Program Files\LibreHardwareMonitor.NET10

ROLLBACK:
- Previous builds overwritten but source preserved in WSL and Windows
- Settings file at %APPDATA%\TURMO\settings.json
- Runtime logs at %LOCALAPPDATA%\TURMO\logs\

NEXT STEPS:
- Physical display acceptance testing
- Mark v0.1.0 STABLE after user confirms all checklist items
- v0.2.0 for feature additions