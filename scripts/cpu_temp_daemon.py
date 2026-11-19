#!/usr/bin/env python3
"""
CPU Temperature Daemon — standalone subprocess for frozen GUI.
- Own process, own .NET init, own main thread (STA via pythonnet)
- Reads CPU temperature ONLY via LibreHardwareMonitor (proven path)
- Never touches COM4, USB, or display monitor
- IPC: stdout JSON lines {"cpu_temp": float, "ts": float} | {"error": str}
- One instance max; GUI spawns, reads stdout, restarts on crash
- Graceful shutdown on stdin close / SIGTERM
"""
import sys
import os
import json
import time
import signal
import threading
from pathlib import Path

# Ensure we can import turmo_runtime from the frozen bundle or venv
# In frozen GUI, this script lives at _MEIPASS/scripts/ or alongside the exe
SCRIPT_DIR = Path(__file__).parent.resolve()
for p in (str(SCRIPT_DIR), str(SCRIPT_DIR.parent), str(SCRIPT_DIR.parent / ".venv-win" / "Lib" / "site-packages")):
    if p not in sys.path:
        sys.path.insert(0, p)

# Silence pythonnet/clr noise
os.environ.setdefault("PYTHONNET_RUNTIME", "coreclr")

def _log(msg: str) -> None:
    # stderr for daemon diagnostics (GUI can capture if needed)
    print(f"[cpu-daemon] {msg}", file=sys.stderr, flush=True)

def run_daemon():
    """Main daemon loop — reads CPU temp every 2s, emits JSON to stdout."""
    _log("starting CPU temperature daemon")
    
    # Import LHM machinery (same proven path as turmo_runtime.py)
    try:
        import pythonnet
        pythonnet.load("coreclr")
        import clr
        # System LHM install (same as _init_libre_hardware_monitor)
        lhm_path = r"C:\Program Files\LibreHardwareMonitor.NET10"
        if not Path(lhm_path).exists():
            _log(f"LHM not found at {lhm_path}")
            sys.exit(1)
        sys.path.append(lhm_path)
        clr.AddReference("LibreHardwareMonitorLib")
        from LibreHardwareMonitor import Hardware
    except Exception as e:
        _log(f"LHM init failed: {e}")
        print(json.dumps({"error": f"LHM init failed: {e}"}), flush=True)
        sys.exit(1)

    computer = None
    try:
        computer = Hardware.Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = False
        computer.IsMemoryEnabled = False
        computer.Open()
        _log("LHM Computer opened successfully")
    except Exception as e:
        _log(f"Computer.Open failed: {e}")
        print(json.dumps({"error": f"Computer.Open failed: {e}"}), flush=True)
        sys.exit(1)

    # Graceful shutdown
    stop_event = threading.Event()
    def _shutdown(*_):
        stop_event.set()
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    # stdin close = parent died (only when piped, not interactive terminal)
    def _watch_stdin():
        try:
            # Check if stdin is a pipe (not interactive terminal)
            if not sys.stdin.isatty():
                data = sys.stdin.read()
                if data == "":
                    stop_event.set()
            # If interactive, don't watch stdin
        except Exception:
            stop_event.set()
    threading.Thread(target=_watch_stdin, daemon=True).start()

    # Main read loop
    while not stop_event.is_set():
        cpu_temp_c = None
        cpu_name = "Unknown CPU"
        try:
            for hardware in computer.Hardware:
                if str(hardware.HardwareType) == "Cpu":
                    hardware.Update()
                    cpu_name = hardware.Name
                    for sensor in hardware.Sensors:
                        if sensor.Value is not None and "Temperature" in str(sensor.SensorType):
                            name = sensor.Name
                            if "Package" in name or "CPU Package" in name:
                                cpu_temp_c = float(sensor.Value)
                                break
                            if "Max" in name and "Core" in name:
                                cpu_temp_c = float(sensor.Value)
                                break
                    if cpu_temp_c is not None:
                        break
        except Exception as e:
            _log(f"read error: {e}")
            print(json.dumps({"error": f"read error: {e}"}), flush=True)
            time.sleep(2)
            continue

        if cpu_temp_c is not None:
            # Sanity check
            if 0 < cpu_temp_c < 120:
                print(json.dumps({"cpu_temp": cpu_temp_c, "ts": time.time(), "cpu_name": cpu_name}), flush=True)
            else:
                _log(f"out-of-range temp {cpu_temp_c}, ignoring")
                print(json.dumps({"error": f"out-of-range temp {cpu_temp_c}"}), flush=True)
        else:
            _log("no CPU temperature sensor found")
            print(json.dumps({"error": "no CPU temperature sensor found"}), flush=True)

        # Wait 2s or until stop
        stop_event.wait(2.0)

    # Cleanup
    try:
        if computer:
            computer.Close()
    except Exception:
        pass
    _log("daemon stopped")


if __name__ == "__main__":
    run_daemon()