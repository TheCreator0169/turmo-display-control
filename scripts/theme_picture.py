"""Pictures for the user's own themes (v0.3.0): the Gallery shows <theme folder>/preview.png, which an official theme
ships but a theme made or copied by the user did not have until it had run in Live Preview. Here it is drawn from
theme.json with demo readings, in a thread, when it is missing or older than the theme."""

import os
import threading
from pathlib import Path

PICTURE = "preview.png"


def needs_picture(folder: Path) -> bool:
    """True when the theme in `folder` has a theme.json and no picture, or a picture older than the theme."""
    try:
        theme = (folder / "theme.json").stat().st_mtime
    except OSError:
        return False
    try:
        return (folder / PICTURE).stat().st_mtime < theme
    except OSError:
        return True


def render_picture(folder: Path, on_error=None) -> bool:
    """Draw the theme in `folder` with demo readings and save <folder>/preview.png. False (and nothing written) when
    it cannot be drawn; never raises. `on_error(where, exc)` is told why."""
    try:
        from scripts import shape_icons
        shape_icons.register()
        from libre_panel.render.renderer import Renderer
        from libre_panel.sensors.demo import demo_snapshot
        from libre_panel.theme.model import load_theme
        renderer = Renderer(load_theme(folder.resolve()), preview=True)
        try:
            frame, _ = renderer.render(demo_snapshot())
        finally:
            renderer.close()
        tmp = folder / f"{PICTURE}.{os.getpid()}.{threading.get_ident()}.tmp"  # one name per writer
        frame.convert("RGB").save(tmp, format="PNG")
        tmp.replace(folder / PICTURE)
        return True
    except Exception as e:
        if on_error:
            try:
                on_error(f"theme picture {folder.name}", e)
            except Exception:
                pass
        return False


class PictureMaker:
    """Draws the missing pictures one theme at a time in a thread. A theme that failed is not tried again until its
    theme.json changes. `poll()` is for the Tk thread: it returns True once, when new pictures were made."""

    def __init__(self, on_error=None):
        self._thread = None
        self._made = 0
        self._on_error = on_error
        self._tried = set()  # (folder, theme.json mtime): each version of a theme is drawn once, however its mtime reads

    def start(self, folders) -> bool:
        """Begin drawing the pictures `folders` need; False when nothing is needed or a run is still going."""
        if self._thread is not None and self._thread.is_alive():
            return False
        todo = []
        for f in map(Path, folders):
            try:
                stamp = (f / "theme.json").stat().st_mtime
            except OSError:
                continue
            if needs_picture(f) and (str(f), stamp) not in self._tried:
                todo.append((f, stamp))
        if not todo:
            return False

        def work():
            for f, stamp in todo:
                self._tried.add((str(f), stamp))  # success or failure: no loop (a theme.json dated in the future stays "newer")
                if render_picture(f, self._on_error):
                    self._made += 1
        self._thread = threading.Thread(target=work, name="theme-pictures", daemon=True)
        self._thread.start()
        return True

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def poll(self) -> bool:
        """True once after a run that made at least one picture (the Gallery redraws then)."""
        if self.running() or not self._made:
            return False
        self._made = 0
        return True
