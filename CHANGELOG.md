TURMO - CHANGELOG
=================


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