#!/usr/bin/env python3
"""Redraw the official theme pictures in previews/ from the current theme.json files (v0.2.9).

The same renderer and demo readings as the GUI's Live Preview. The Gallery shows these pictures, and
`TURMO-Monitor --once` sends them to the LCD. The old pictures are kept in previews/old.

Run:  .venv-win\\Scripts\\python.exe scripts\\make_previews.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "vendor"))
sys.path.insert(0, str(ROOT / "scripts"))
os.chdir(ROOT)

from libre_panel.render.renderer import Renderer  # noqa: E402
from libre_panel.sensors.demo import demo_snapshot  # noqa: E402
from libre_panel.theme.model import load_theme  # noqa: E402

NAMES = ["clean-white", "cyberpunk-neon", "futuristic-hud", "hardware-dashboard", "matrix-terminal",
         "minimal-dark", "rgb-gaming", "custom-blank-canvas"]
SIZES = {"": (480, 320), "-320x480": (320, 480)}  # landscape, portrait


def main():
    for name in NAMES:
        for suffix, size in SIZES.items():
            theme = load_theme((ROOT / "themes" / f"{name}{suffix}").resolve())
            renderer = Renderer(theme, preview=True)
            frame, _ = renderer.render(demo_snapshot())
            renderer.close()
            assert frame.size == size, (name, suffix, frame.size)
            frame.save(ROOT / "previews" / f"{name}{suffix}.png")
            print(f"{name}{suffix}.png {frame.size}")


if __name__ == "__main__":
    main()
