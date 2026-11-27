"""Live Preview page and its worker (v0.2.3): methods of TurmoApp, mixed in."""

from scripts.gui_common import *  # noqa: F401,F403
from scripts.theme_editor import tk_colour  # noqa: E402


class PreviewPage:
    """Methods of TurmoApp (mixed in), moved out of turmo_app_enhanced.py in v0.2.3."""

    def build_preview_tab(self, nb):
        """Live preview tab (v0.2.0 design): a Display card on the left (orientation, brightness,
        refresh, capture, pixel test), the device frame and the sensor values on the right.
        The controls use the same variables and handlers as the Monitor and Settings tabs."""
        if not hasattr(self, "brightness_var"):
            self.brightness_var = tk.IntVar(value=self.settings.brightness)
        bg0, bg2 = PALETTE["bg0"], PALETTE["bg2"]
        small = (self.ui_font, 9)
        frame = tk.Frame(nb, bg=bg0)
        nb.add(frame, text="Live Preview")
        body = tk.Frame(frame, bg=bg0)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)

        card = RoundedCard(body, bg2, PALETTE["line"], bg0, width=300)
        card.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16), anchor="n")
        side = card.inner

        def label(text, top):
            tk.Label(side, text=text, bg=bg2, fg=PALETTE["muted"], font=small).pack(anchor="w", padx=16, pady=(top, 6))

        tk.Label(side, text=tr("Display"), bg=bg2, fg=PALETTE["text"], font=(self.ui_semibold, 11)).pack(
            anchor="w", padx=16, pady=(16, 0))
        label(tr("Orientation"), 12)
        orient = Segmented(side, [(True, tr("Landscape")), (False, tr("Portrait"))], self.landscape_var.get(),
                           lambda _v: self.on_orientation_change(), bg2, small, variable=self.landscape_var)
        orient.stretch()
        orient.pack(fill=tk.X, padx=16)
        label("Brightness", 14)
        bright = tk.Frame(side, bg=bg2)
        bright.pack(fill=tk.X, padx=(16 - Slider.PAD, 14))  # the track starts PAD px inside its canvas; the % ink ends at x=16
        self.preview_bright_label = tk.Label(bright, text=f"{self.brightness_var.get()}%", bg=bg2,
                                             fg=PALETTE["text"], font=("Cascadia Code", 10), width=5, anchor="e", padx=0)
        self.preview_bright_label.pack(side=tk.RIGHT)
        self.brightness_var.trace_add("write", lambda *a: self.preview_bright_label.config(
            text=f"{int(self.brightness_var.get())}%"))
        Slider(bright, 10, 100, self.brightness_var.get(), self.on_brightness_change, bg2,
               variable=self.brightness_var, step=1, width=1).pack(side=tk.LEFT, fill=tk.X, expand=True)
        label("Refresh", 14)
        refresh = Segmented(side, [(250, "250 ms"), (500, "500 ms"), (1000, "1 s"), (2000, "2 s")],
                            self.refresh_var.get(), lambda _v: self.on_refresh_change(), bg2, small,
                            variable=self.refresh_var)
        refresh.stretch()
        refresh.pack(fill=tk.X, padx=16)
        tk.Frame(side, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=16, pady=(18, 16))
        make_button(side, tr("Capture"), self.save_preview_screenshot, (self.ui_font, 10), variant="primary",
                    backdrop=bg2).pack(fill=tk.X, padx=16)
        make_button(side, tr("Pixel test"), self.send_test_image, (self.ui_font, 10), variant="ghost",
                    backdrop=bg2).pack(fill=tk.X, padx=16, pady=(8, 0))

        # Read-only reminders under the buttons: the preview's state, the device, the active theme
        mono = ("Cascadia Code", 9)
        self._pv = {}

        def divider():
            tk.Frame(side, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=16, pady=(14, 10))

        def fact(key, label):
            row = tk.Frame(side, bg=bg2)
            row.pack(fill=tk.X, padx=16, pady=2)
            tk.Label(row, text=label, bg=bg2, fg=PALETTE["muted"], font=small).pack(side=tk.LEFT)
            self._pv[key] = tk.Label(row, text=NO_VALUE, bg=bg2, fg=PALETTE["text"], font=mono)
            self._pv[key].pack(side=tk.RIGHT)

        divider()
        state_row = tk.Frame(side, bg=bg2)
        state_row.pack(fill=tk.X, padx=16, pady=2)
        tk.Label(state_row, text=tr("Preview"), bg=bg2, fg=PALETTE["muted"], font=small).pack(side=tk.LEFT)
        self._pv["state"] = tk.Label(state_row, text="stopped", bg=bg2, fg=PALETTE["text"], font=mono)
        self._pv["state"].pack(side=tk.RIGHT)
        self._pv["dot"] = tk.Label(state_row, text="●", bg=bg2, fg=PALETTE["dim"], font=(self.ui_font, 8))
        self._pv["dot"].pack(side=tk.RIGHT, padx=(0, 6))
        fact("frames", tr("Frames"))
        fact("fps", tr("Real FPS"))
        divider()
        fact("port", "Port")
        fact("size", tr("Resolution"))
        divider()
        tk.Label(side, text=tr("Active theme"), bg=bg2, fg=PALETTE["muted"], font=small, anchor="w").pack(
            fill=tk.X, padx=16)
        self._pv["theme"] = tk.Label(side, text="", bg=bg2, fg=PALETTE["text"], font=(self.ui_semibold, 10),
                                     anchor="w")
        self._pv["theme"].pack(fill=tk.X, padx=16, pady=(4, 6))
        self._pv["strip"] = tk.Frame(side, bg=bg2)
        self._pv["strip"].pack(fill=tk.X, padx=16)
        links = tk.Frame(side, bg=bg2)
        links.pack(fill=tk.X, padx=16, pady=(10, 16))
        links.columnconfigure(0, weight=1, uniform="pvlink")
        links.columnconfigure(1, weight=1, uniform="pvlink")
        make_button(links, tr("Change theme"), lambda: self.select_tab(3), small, variant="ghost", backdrop=bg2,
                    small=True).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        make_button(links, "Theme Editor", lambda: self.select_tab(self.nb.index(self.editor_frame)), small,
                    variant="ghost", backdrop=bg2, small=True).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self._pv_theme, self._pv_last = None, (time.monotonic(), 0)
        self._refresh_preview_info()

        stage = tk.Frame(body, bg=bg0)
        stage.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ctrl = tk.Frame(stage, bg=bg0)
        ctrl.pack(fill=tk.X, pady=(0, 12))
        make_button(ctrl, tr("Start Preview"), self.start_preview, (self.ui_font, 10), variant="primary",
                    backdrop=bg0).pack(side=tk.LEFT)
        make_button(ctrl, tr("Stop Preview"), self.stop_preview, (self.ui_font, 10), variant="danger",
                    backdrop=bg0).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(ctrl, text=tr("FPS"), bg=bg0, fg=PALETTE["muted"], font=small).pack(side=tk.LEFT, padx=(20, 6), pady=(0, 2))
        self.fps_var = tk.DoubleVar(value=2.0)
        fps_label = tk.Label(ctrl, text="2.0", bg=bg0, fg=PALETTE["text"], font=("Cascadia Code", 10),
                             width=4, anchor="e")
        self.fps_var.trace_add("write", lambda *a: fps_label.config(text=f"{self.fps_var.get():.1f}"))
        fps_label.pack(side=tk.RIGHT, pady=(0, 2))  # ends at the bezel's right edge; 2 px up centres the digits on the bar
        Slider(ctrl, 0.5, 10, 2.0, None, bg0, variable=self.fps_var, step=0.5, width=150).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        # Device frame: a dark bezel (radius 14) around the canvas that shows the frame
        bezel = RoundedCard(stage, "#0B0E14", PALETTE["line2"], bg0, radius=18)
        bezel.pack(fill=tk.BOTH, expand=True)
        self.preview_canvas = tk.Canvas(bezel.inner, width=1, height=1, bg="#05070B", highlightthickness=0, bd=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.preview_canvas.bind("<Configure>", self.on_preview_resize)
        self.preview_caption = tk.Label(stage, text="", bg=bg0, fg=PALETTE["muted"], font=small)
        self.preview_caption.pack(pady=(8, 0))
        self._refresh_preview_caption()

        sensors_card = RoundedCard(stage, bg2, PALETTE["line"], bg0)
        sensors_card.pack(fill=tk.X, pady=(12, 0))
        grid = tk.Frame(sensors_card.inner, bg=bg2)
        grid.pack(fill=tk.X, padx=16, pady=12)
        self.sensor_vars = {}
        sensors = ["cpu.load", "cpu.temp", "gpu.load", "gpu.temp", "mem.load", "mem.used", "net.down", "net.up"]
        for c in range(4):
            grid.columnconfigure(c, weight=1, uniform="sensor")
        for i, s in enumerate(sensors):
            var = tk.StringVar(value=NO_VALUE)
            self.sensor_vars[s] = var
            row, col = divmod(i, 4)
            cell = tk.Frame(grid, bg=bg2)
            cell.grid(row=row, column=col, sticky="ew", pady=3)
            tk.Label(cell, text=s, bg=bg2, fg=PALETTE["muted"], font=small).pack(fill=tk.X)
            tk.Label(cell, textvariable=var, bg=bg2, fg=PALETTE["text"], font=("Cascadia Code", 10)).pack(fill=tk.X)

    def _refresh_preview_info(self):
        """The Live Preview card's reminders: state, frames, real frame rate, port, resolution, theme colours."""
        pv = getattr(self, "_pv", None)
        if not pv:
            return
        running = self.preview_running
        frames = getattr(self, "_frame_count", 0)
        now = time.monotonic()
        last_t, last_n = self._pv_last
        rate = (frames - last_n) / (now - last_t) if running and now > last_t else 0.0
        self._pv_last = (now, frames)
        pv["state"].config(text="running" if running else "stopped")
        pv["dot"].config(fg=PALETTE["green"] if running else PALETTE["dim"])
        pv["frames"].config(text=f"#{frames}")
        pv["fps"].config(text=f"{rate:.1f}" if running else NO_VALUE)
        pv["port"].config(text=self.port_var.get().replace(" ✓", "").split(" ")[0] or NO_VALUE)
        pv["size"].config(text="480 × 320" if self.settings.orientation == "landscape" else "320 × 480")
        slug = self.settings.theme
        if slug != self._pv_theme:  # the name and the three colours of the gallery tile
            self._pv_theme = slug
            try:
                meta = json.loads((theme_paths.folder(DATA_ROOT / "themes", slug) / "theme.json").read_text(encoding="utf-8"))
            except Exception as _e:
                log_swallowed("preview theme meta", _e)
                meta = {}
            pal, bg2 = meta.get("palette", {}), PALETTE["bg2"]
            pv["theme"].config(text=meta.get("name", slug))
            for child in pv["strip"].winfo_children():
                child.destroy()
            for colour in (pal.get("accent", PALETTE["cyan"]), pal.get("bg", PALETTE["bg0"]),
                           mix(PALETTE["text"], bg2, 0.3)):
                tk.Frame(pv["strip"], bg=tk_colour(colour), height=8).pack(
                    side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

    def _refresh_preview_caption(self):
        """The line under the device frame: orientation, resolution and whether the preview runs."""
        caption = getattr(self, "preview_caption", None)
        if caption is None:
            return
        landscape = self.settings.orientation == "landscape"
        caption.config(text="{} \u00b7 {} \u00b7 {}".format(
            tr("Landscape") if landscape else tr("Portrait"), "480 \u00d7 320" if landscape else "320 \u00d7 480",
            tr("Preview running") if self.preview_running else tr("Preview stopped")))

    def save_preview_screenshot(self):
        """Save the last rendered preview frame as a PNG (the Live Preview 'Screenshot' button)."""
        frame = getattr(self, "_preview_frame", None)
        if frame is None:
            self.show_info(tr("Screenshot"), tr("Start the preview first."))
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", initialfile="turmo_screenshot.png",
                                            filetypes=[("PNG image", "*.png")])
        if path:
            try:
                frame.save(path)
            except (OSError, ValueError) as e:
                self.show_error(tr("Could not save the screenshot"), tr(friendly_error(e)))
                return
            self.status_var.set(tr("Screenshot saved: {path}").format(path=path))

    def start_preview(self):
        if self.preview_running:
            return
        # ponytail: backoff — don't restart a worker that keeps dying
        if hasattr(self, '_preview_cooldown_until') and time.time() < self._preview_cooldown_until:
            self.status_var.set(tr("Preview paused (cooldown: {seconds}s)").format(seconds=int(self._preview_cooldown_until - time.time())))
            return
        self.preview_running = True
        self.status_var.set(tr("Preview running"))
        self._refresh_preview_caption()
        # ponytail: background worker produces frames, main-thread timer displays them
        self._preview_frame = None
        self._preview_readings = {}
        self._preview_lock = threading.Lock()
        self._preview_err = None
        self._preview_ready = False  # ponytail: set after first worker read cycle
        # One generation per start: a worker or UI tick from an older start stops itself,
        # so restarts never leave two workers writing the same history and renderer.
        self._preview_gen = getattr(self, "_preview_gen", 0) + 1
        gen = self._preview_gen
        previous = getattr(self, "_preview_worker_thread", None)
        self._preview_worker_thread = threading.Thread(
            target=self._preview_worker, args=(gen, previous), daemon=True)
        self._preview_worker_thread.start()
        _log_event("PREVIEW_START", f"gen={gen}")
        # ponytail: defer first UI tick until worker has produced initial readings
        self.root.after(500, lambda: self._preview_ui_tick(gen))

    def stop_preview(self):
        _log_event("PREVIEW_STOP", f"gen={getattr(self, '_preview_gen', 0)}")
        self.preview_running = False
        self.status_var.set(tr("Preview stopped"))
        self._refresh_preview_caption()

    def restart_preview(self):
        self.stop_preview()
        self.root.after(200, self.start_preview)

    def _preview_worker(self, gen=0, previous=None):
        """Background thread: read sensors + render frames, store latest under lock."""
        # Wait for the previous worker to leave its loop: one active worker at a time.
        if previous is not None:
            previous.join(timeout=3.0)
        if gen != self._preview_gen or not self.preview_running:
            return
        try:
            from scripts import shape_icons
            shape_icons.register()
            from libre_panel.theme.model import load_theme as lp_load_theme
            from libre_panel.render.renderer import Renderer
            from libre_panel.sensors.base import Snapshot, Reading
            from libre_panel.sensors.psutil_provider import PsutilProvider
            from collections import defaultdict
        except ImportError as e:
            self._preview_err = f"ImportError: {e}"  # ok: the error is kept in _preview_err and shown
            return

        try:
            # Portrait uses the <theme>-320x480 folder when it exists. The renderer is
            # rebuilt when the theme or the orientation changes.
            theme_name = self.settings.theme
            if self.settings.orientation == "portrait" and theme_paths.folder(DATA_ROOT / "themes", f"{theme_name}-320x480").is_dir():
                theme_name = f"{theme_name}-320x480"
            if not hasattr(self, '_preview_renderer') or getattr(self, '_preview_renderer_key', None) != theme_name:
                theme_path = theme_paths.folder(DATA_ROOT / "themes", theme_name)
                try:
                    theme = lp_load_theme(theme_path)
                except Exception as e:
                    self._preview_err = f"Theme load: {e}"  # ok: the error is kept in _preview_err and shown
                    return
                self._preview_renderer = Renderer(theme, preview=True)
                self._preview_unit_cache = {}
                self._preview_celsius_only = keeps_celsius(theme_path)  # a "temps" module is Celsius-only
                self._preview_renderer_key = theme_name
                self._preview_provider = PsutilProvider()
                self._preview_hist = defaultdict(list)
                self._preview_max_hist = 600
        except Exception as e:
            self._preview_err = f"Worker init: {e}"
            if RUNTIME_LOGGING_AVAILABLE:
                log_runtime("PREVIEW", "WORKER_INIT_ERROR", str(e), exc=e)
            return

        renderer = self._preview_renderer
        provider = self._preview_provider

        def read_gpu():
            try:
                import pynvml
                if not self._pynvml_init:  # was hasattr(): always True, so NVML was never initialised
                    pynvml.nvmlInit()
                    self._pynvml_init = True
                h = pynvml.nvmlDeviceGetHandleByIndex(self.settings.gpu_index)
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                temp = pynvml.nvmlDeviceGetTemperature(h, 0)
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                return {
                    "gpu.load": Reading(key="gpu.load", value=float(util.gpu), unit="%", label="GPU load"),
                    "gpu.temp": Reading(key="gpu.temp", value=float(temp), unit="\u00b0C", label="GPU temperature"),
                    "gpu.vram_used": Reading(key="gpu.vram_used", value=mem.used / (1024**3), unit="GB", label="VRAM used"),
                    "gpu.vram_total": Reading(key="gpu.vram_total", value=mem.total / (1024**3), unit="GB", label="VRAM total"),
                }
            except Exception as _e:
                log_swallowed("preview readings", _e)
                return {}

        def read_cpu_temp():
            try:
                from turmo_runtime import read_cpu_temperature
                result = read_cpu_temperature()
                if RUNTIME_LOGGING_AVAILABLE:
                    log_runtime("PREVIEW", "CPU_TEMP", f"result keys={list(result.keys()) if isinstance(result, dict) else type(result).__name__}")
                return result if result and isinstance(result, dict) else {}
            except Exception as e:
                if RUNTIME_LOGGING_AVAILABLE:
                    log_runtime("PREVIEW", "CPU_TEMP_ERROR", str(e), exc=e)
                try:
                    from scripts.turmo_runtime import read_cpu_temperature
                    result = read_cpu_temperature()
                    if RUNTIME_LOGGING_AVAILABLE:
                        log_runtime("PREVIEW", "CPU_TEMP_FALLBACK", f"result keys={list(result.keys()) if isinstance(result, dict) else type(result).__name__}")
                    return result if result and isinstance(result, dict) else {}
                except Exception as e2:
                    if RUNTIME_LOGGING_AVAILABLE:
                        log_runtime("PREVIEW", "CPU_TEMP_FALLBACK_ERROR", str(e2), exc=e2)
                    return {}

        while self.preview_running and gen == self._preview_gen:
            try:
                readings = dict(provider.read())
                readings.update(read_gpu())
                readings.update(read_cpu_temp())
                if RUNTIME_LOGGING_AVAILABLE and len(readings) > 0:
                    log_runtime("PREVIEW", "READINGS_KEYS", f"keys={list(readings.keys())}")

                for k, r in readings.items():
                    if isinstance(r.value, (int, float)):
                        h = self._preview_hist[k]
                        h.append(float(r.value))
                        if len(h) > self._preview_max_hist:
                            h.pop(0)

                unit = "celsius" if getattr(self, "_preview_celsius_only", False) else self.temp_unit_for_thread()
                shown, shown_hist = temps_in_unit(readings, self._preview_hist, unit)  # as the Monitor does
                snap = Snapshot(readings=shown, history=dict(shown_hist))
                frame, _ = renderer_for_unit(renderer, unit, self._preview_unit_cache, lambda t: Renderer(t, preview=True)).render(snap)
                frame = frame.convert("RGB")
                self._save_theme_picture(theme_name, frame)  # before the dimming: the picture is the theme, not the brightness
                frame = dim_image(frame, self.settings.brightness)  # same dimming as the Monitor

                with self._preview_lock:
                    self._preview_frame = frame
                    self._frame_count = getattr(self, "_frame_count", 0) + 1
                    self._preview_readings = readings
                    self._preview_ready = True  # ponytail: worker has produced first readings
            except Exception as e:
                self._preview_err = str(e)
                if "numpy" in str(e).lower():
                    return  # permanent packaging failure, stop worker

            time.sleep(1.0)  # ponytail: 1 Hz sensor refresh; main thread controls display rate

    def _save_theme_picture(self, theme_name, frame):
        """Worker thread: once a theme of the user has run, keep its picture in its own folder (preview.png) for the
        gallery, which has none for it until then. Written again when its theme.json is newer than the picture."""
        try:
            if not theme_paths.is_custom(theme_name):
                return  # the official themes ship their pictures
            folder = theme_paths.custom_dir() / theme_name
            stamp = (folder / "theme.json").stat().st_mtime
            if getattr(self, "_picture_seen", None) == (theme_name, stamp):
                return  # looked at already for this version of the theme
            self._picture_seen = (theme_name, stamp)
            picture = folder / "preview.png"
            if picture.is_file() and picture.stat().st_mtime >= stamp:
                return
            frame.save(picture)
            self._picture_new = True  # the main thread redraws the gallery
        except Exception as e:
            log_swallowed("theme picture", e)

    def _preview_ui_tick(self, gen=None):
        """Main thread: display latest frame + update sensor vars."""
        if not self.preview_running or (gen is not None and gen != self._preview_gen):
            return
        if getattr(self, "_picture_new", False):
            self._picture_new = False
            if hasattr(self, "_gallery_grid"):
                self._gallery_render()

        # ponytail: wait for worker to produce first readings
        if not self._preview_ready:
            self.root.after(500, lambda: self._preview_ui_tick(gen))
            return

        with self._preview_lock:
            frame = self._preview_frame
            readings = self._preview_readings
        err = self._preview_err

        if err:
            self._preview_err = None
            self.status_var.set(tr("Preview error: {reason}").format(reason=tr(friendly_error(err))))
            self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Preview ERROR: {err}\n")
            self.log_text.see(tk.END)
            # ponytail: backoff — if the worker keeps dying, pause restarts for 15s
            self._preview_cooldown_until = time.time() + 15.0
            self.status_var.set(tr("Preview paused (cooldown: {seconds}s)").format(seconds=15))
            # ponytail: reschedule so a transient error can recover on next tick
            self.root.after(5000, lambda: self._preview_ui_tick(gen))
            return

        if frame is not None:
            # Tk widget updates — main thread only
            for k, r in readings.items():
                if k in self.sensor_vars and isinstance(r.value, (int, float)):
                    if "temp" in k:
                        fahrenheit = self.temp_unit() == "fahrenheit"
                        self.sensor_vars[k].set(f"{temp_in(r.value, self.temp_unit()):.1f}" + ("\u00b0F" if fahrenheit else "\u00b0C"))
                    elif "load" in k or "mem.load" == k:
                        self.sensor_vars[k].set(f"{r.value:.0f}%")
                    elif "used" in k or "vram_used" == k:
                        self.sensor_vars[k].set(f"{r.value:.1f} GB")
                    elif "down" in k or "up" in k:
                        self.sensor_vars[k].set(format_rate(r.value))
                    else:
                        self.sensor_vars[k].set(f"{r.value:.2f}")

            canvas_w = self.preview_canvas.winfo_width()
            canvas_h = self.preview_canvas.winfo_height()
            if canvas_w > 10 and canvas_h > 10:
                # Keep the frame's aspect ratio: a portrait frame must not be stretched
                # to the landscape canvas.
                scale = min(canvas_w / frame.width, canvas_h / frame.height)
                size = (max(1, int(frame.width * scale)), max(1, int(frame.height * scale)))
                resized = frame.resize(size, Image.LANCZOS)
                photo = ImageTk.PhotoImage(resized)
                self.update_preview(photo)

        delay_ms = int(1000.0 / max(0.1, self.fps_var.get()))
        self.root.after(delay_ms, lambda: self._preview_ui_tick(gen))

    def update_preview(self, photo):
        if not self.preview_running:
            return
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(
            self.preview_canvas.winfo_width() // 2,
            self.preview_canvas.winfo_height() // 2,
            image=photo, anchor=tk.CENTER
        )
        self.preview_canvas.image = photo  # Keep reference

    def on_preview_resize(self, event):
        pass  # Preview regenerates on next loop
