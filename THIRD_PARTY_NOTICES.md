# Third-party notices

TURMO is GPL-3.0-or-later (`LICENSE`). The exes bundle the parts below. Source code of TURMO: this repository, at the tag of the version you have.

| Part | Licence | Where |
|---|---|---|
| libre_panel (sensors, RGB565, display protocol) | GPL-3.0-or-later | `scripts\vendor\libre_panel`; its full credits (turing-smart-screen-python, SPUR II, InfoPanel, liquidctl and others) are in `scripts\vendor\libre_panel\assets\NOTICE.md` |
| LibreHardwareMonitor library and helper DLLs (RAMSPDToolkit, DiskInfoToolkit, BlackSharp) | MPL-2.0 | `scripts\vendor\lhm`, passed on unchanged; source: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor |
| HidSharp | Apache-2.0 | `scripts\vendor\lhm` |
| System.* .NET libraries | MIT | `scripts\vendor\lhm` |
| Meteocons (weather icons) | MIT, Copyright (c) 2020-present Bas Milius | via libre_panel |
| Python, Tk, Pillow, psutil, pyserial, pystray and other Python packages | their own licences (PSF, HPND, BSD, LGPL) | bundled by PyInstaller |

PawnIO (driver by namazso, GPL-2.0-or-later with a module exception, https://pawnio.eu) is **not** shipped. TURMO reads the CPU temperature through it when the user has installed it from the official source.

This list is made by hand from the files of the repository; it is not legal advice.
