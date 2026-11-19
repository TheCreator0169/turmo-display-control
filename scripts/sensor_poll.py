"""Sensors for the Dashboard while Live Preview is off (v0.2.6).

Before, with Live Preview off only CPU load and RAM had values: CPU temperature, GPU, VRAM, disk and network showed a
dash, because only the preview worker read them. `SensorPoller` reads them once a second on its own thread (the CPU
temperature helper is a socket call that can wait up to a second, NVML can be slow to start: neither may run on the Tk
thread) and only while it is wanted: the window is visible and the Live Preview is not running (the preview reads the
same sensors itself, and psutil's CPU percentage is shared by every caller in the process, so two readers would spoil
each other's figure).

`read` returns (readings, reasons): readings maps a key to a Reading or a number (`latest` gives plain numbers), reasons maps a missing key (or a
prefix such as "gpu.") to a short text that says why it has no value.
"""
import threading
import time

NVML_REASON_MISSING = "No NVIDIA GPU or driver found (NVML is not available)"
CPU_TEMP_REASON = "The CPU temperature helper is not answering (start it from Settings, or see Diagnostics)"


class SensorPoller:
    def __init__(self, read, wanted, interval=1.0):
        self._read, self._wanted, self._interval = read, wanted, interval
        self._lock = threading.Lock()
        self._thread = None
        self._readings, self._reasons, self._stamp = {}, {}, 0.0

    def ensure_running(self):
        """Called every second by the Dashboard loop: start the thread when it is wanted and not running."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if not self._wanted():
                return
            self._thread = threading.Thread(target=self._loop, name="sensor-poller", daemon=True)
            self._thread.start()

    def running(self):
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def latest(self):
        """The last readings, or {} when there are none yet or they are older than three intervals."""
        with self._lock:
            if time.time() - self._stamp > 3 * self._interval:
                return {}
            return dict(self._readings)

    def reasons(self):
        with self._lock:
            return dict(self._reasons)

    def _loop(self):
        while self._wanted():
            try:
                readings, reasons = self._read()
                # plain numbers, as psutil gives them: the quick panel and the minimal view compare them
                readings = {k: getattr(v, "value", v) for k, v in readings.items()}
                with self._lock:
                    self._readings, self._reasons, self._stamp = readings, dict(reasons), time.time()
            except Exception as e:  # keep polling; the reason shows instead of a silent blank
                with self._lock:
                    self._reasons = {"": f"Sensor read failed: {e}"}
            time.sleep(self._interval)


def reason_for(reasons, key):
    """Why `key` has no value: an exact entry, else the one for its group ("gpu." for "gpu.temp"), else the generic."""
    if key in reasons:
        return reasons[key]
    group = key.split(".")[0] + "."
    return reasons.get(group) or reasons.get("") or ""


def read_nvml(gpu_index, state):
    """GPU load, temperature and VRAM through NVML: (readings, reasons). `state` is a dict kept between calls
    (NVML is started once). Without an NVIDIA GPU or driver the reasons say so and readings is empty."""
    from libre_panel.sensors.base import Reading
    try:
        import pynvml
        if not state.get("init"):
            pynvml.nvmlInit()
            state["init"] = True
        count = pynvml.nvmlDeviceGetCount()
        handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index if gpu_index < count else 0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, 0)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
    except Exception as e:  # ImportError, NVMLError (no driver, no GPU), anything else: say which
        return {}, {"gpu.": f"{NVML_REASON_MISSING}: {type(e).__name__}"}
    gib = 1024 ** 3
    return {
        "gpu.load": Reading(key="gpu.load", value=float(util.gpu), unit="%", label="GPU load"),
        "gpu.temp": Reading(key="gpu.temp", value=float(temp), unit="°C", label="GPU temperature"),
        "gpu.vram_used": Reading(key="gpu.vram_used", value=mem.used / gib, unit="GB", label="VRAM used"),
        "gpu.vram_total": Reading(key="gpu.vram_total", value=mem.total / gib, unit="GB", label="VRAM total"),
    }, {}


def make_reader(settings, read_cpu_temperature):
    """The `read` function for SensorPoller: psutil (loads, memory, disk, network rates), NVML and the CPU
    temperature helper. `settings` is read each call (the GPU index can change); `read_cpu_temperature` is
    turmo_runtime's. The psutil provider is made once: network and disk rates need two reads."""
    from libre_panel.sensors.psutil_provider import PsutilProvider
    provider, nvml = PsutilProvider(), {}

    def read():
        readings, reasons = dict(provider.read()), {}
        gpu, why = read_nvml(settings.gpu_index, nvml)
        readings.update(gpu)
        reasons.update(why)
        temp = read_cpu_temperature() or {}
        readings.update(temp)
        if "cpu.temp" not in temp:
            reasons["cpu.temp"] = CPU_TEMP_REASON
        return readings, reasons
    return read
