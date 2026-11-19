#!/usr/bin/env python3
"""TURMO CPU Temperature Helper (elevated).

Serves CPU temp on 127.0.0.1:18234. Protocol: client sends b"GET\\n",
server replies with ONE line of JSON:
  {"cpu_temp": 45.2, "cpu_name": "AMD Ryzen 9 7950X", "sensors": 5,
   "elevated": true, "ts": 1700000000.0}
Read-only. No commands. No auth. Loopback only.

DESIGN NOTE (BUG-016 timeout root-cause fix):
LHM's Computer.Update() is the slow path. It MUST NOT run between
socket.listen() and the accept loop, nor synchronously on every GET
(a slow Update() > client read-timeout => connect-OK + read-timeout).
Instead a background updater thread keeps a cache warm; the accept
loop sends the cached value IMMEDIATELY after accept(). A stale cache
(old ts) is treated as unavailable by the GUI.

ponytail: TCP loopback + a single background updater thread - stdlib only.
"""
import ctypes
import json
import os
import socket
import subprocess
import sys
import threading
import time

PORT = 18234
HOST = "127.0.0.1"

# Warm cache, refreshed by the background updater thread every ~1s.
# The accept loop only ever reads from this dict - it never blocks on LHM.
_cache = {"temp": None, "name": "Unknown CPU", "count": 0, "ts": 0.0,
          "sensor": None, "sensor_id": None, "selection": "none"}


def _log(msg):
    """Log to stderr AND to a helper.log next to the exe/script (elevated can write)."""
    print(msg, file=sys.stderr, flush=True)
    try:
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "helper.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def find_lhm_dir():
    """Find LHM DLLs. ponytail: same candidate paths as turmo_runtime.
    Prefers the VENDED LHM (bundled 0.9.6.0) over any system install."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        exedir = os.path.dirname(sys.executable)
        # onedir helper: DLLs live next to the exe (no user-writable temp extraction)
        for d in (os.path.join(meipass, "lhm"),
                  os.path.join(exedir, "lhm"),
                  os.path.join(exedir, "_internal", "lhm")):
            if os.path.isfile(os.path.join(d, "LibreHardwareMonitorLib.dll")):
                return d
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        for d in (os.path.join(script_dir, "vendor", "lhm"),
                  os.path.join(script_dir, "..", "vendor", "lhm")):
            if os.path.isfile(os.path.join(d, "LibreHardwareMonitorLib.dll")):
                return d
    return None


def _pawnio_info():
    """Return (present: bool, state: str) for the PawnIO service.

    ponytail: sc.exe query - no extra deps; state is the raw STATE token.
    """
    try:
        out = subprocess.check_output(["sc.exe", "query", "PawnIO"],
                                      text=True, timeout=5,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return False, "MISSING"
    present = "SERVICE_NAME" in out and "does not exist" not in out.lower()
    state = "UNKNOWN"
    for line in out.splitlines():
        if line.strip().startswith("STATE"):
            state = line.split(":", 1)[1].strip()
            break
    return present, state


def init_lhm():
    """Load LHM via coreclr. Returns (Computer, lhm_dir) or (None, None)."""
    lhm_dir = find_lhm_dir()
    if lhm_dir is None:
        _log("LHM DLLs not found in any candidate dir")
        return None, None
    if lhm_dir not in sys.path:
        sys.path.append(lhm_dir)
    import pythonnet
    pythonnet.load("coreclr")
    import clr
    for lib in ("LibreHardwareMonitorLib", "DiskInfoToolkit"):
        dll = os.path.join(lhm_dir, lib + ".dll")
        if os.path.isfile(dll):
            clr.AddReference(dll)
    from LibreHardwareMonitor.Hardware import Computer
    c = Computer()
    c.IsCpuEnabled = True
    c.IsGpuEnabled = False
    c.IsMemoryEnabled = False
    c.Open()
    return c, lhm_dir


# CPU package sensors, most preferred first (LibreHardwareMonitor names).
# Intel: "CPU Package". AMD Zen: "Core (Tctl/Tdie)" / "Tctl/Tdie".
PACKAGE_SENSOR_NAMES = ("CPU Package", "Core (Tctl/Tdie)", "Tctl/Tdie", "CPU Die")


def harvest_cpu_temp(computer):
    """Refresh CPU hardware and pick one temperature. Returns a dict:
    temp (float or None), name (CPU), count (temperature sensors seen),
    sensor (LHM sensor name), sensor_id (LHM identifier = source),
    selection ("package" | "max" | "none").
    Prefers a real CPU package sensor. Only if none exists, uses the
    highest CPU temperature (labelled "max"). No values are invented."""
    cpu_name = "Unknown CPU"
    temps = []  # (value, sensor name, sensor identifier)
    by_name = {}
    for hw in computer.Hardware:
        if str(hw.HardwareType) != "Cpu":
            continue
        hw.Update()
        cpu_name = hw.Name
        for sub in hw.SubHardware:
            sub.Update()
        for h in [hw, *hw.SubHardware]:
            for s in h.Sensors:
                if str(s.SensorType) != "Temperature" or s.Value is None:
                    continue
                item = (float(s.Value), str(s.Name), str(s.Identifier))
                temps.append(item)
                by_name.setdefault(str(s.Name), item)
    base = {"name": cpu_name, "count": len(temps)}
    for wanted in PACKAGE_SENSOR_NAMES:
        if wanted in by_name:
            v, sname, sid = by_name[wanted]
            return {**base, "temp": v, "sensor": sname, "sensor_id": sid, "selection": "package"}
    if temps:
        v, sname, sid = max(temps)
        return {**base, "temp": v, "sensor": sname, "sensor_id": sid, "selection": "max"}
    return {**base, "temp": None, "sensor": None, "sensor_id": None, "selection": "none"}


def _updater_loop(computer, stop):
    """Background thread: keep _cache warm. LHM Update() happens HERE,
    never on the socket thread. Logs only when the chosen sensor changes."""
    last = None
    while not stop.is_set():
        try:
            r = harvest_cpu_temp(computer)
            _cache.update(temp=r["temp"], name=r["name"], count=r["count"],
                          sensor=r["sensor"], sensor_id=r["sensor_id"],
                          selection=r["selection"], ts=time.time())
            key = (r["sensor"], r["selection"])
            if key != last:
                _log(f"sensor selected: {r['sensor']!r} selection={r['selection']} "
                     f"source={r['sensor_id']} (of {r['count']} temperature sensors)")
                last = key
        except Exception as e:
            _log(f"updater error: {e}")
        time.sleep(1.0)


def selftest():
    """In-process LHM read, no socket. For: run ELEVATED, verify CPU name + sensors.
    Also lists every CPU temperature sensor so the package choice can be checked."""
    computer, lhm_dir = init_lhm()
    if computer is None:
        _log("SELFTEST FAIL: LHM init failed")
        print(json.dumps({"ok": False, "reason": "LHM init failed",
                          "elevated": _is_elevated(), "lhm_dir": lhm_dir}))
        return 1
    try:
        r = harvest_cpu_temp(computer)
        all_temps = []
        for hw in computer.Hardware:
            if str(hw.HardwareType) == "Cpu":
                for h in [hw, *hw.SubHardware]:
                    for s in h.Sensors:
                        if str(s.SensorType) == "Temperature":
                            all_temps.append({"name": str(s.Name), "id": str(s.Identifier),
                                              "value": None if s.Value is None else float(s.Value)})
    finally:
        computer.Close()
    present, state = _pawnio_info()
    out = {
        "ok": r["count"] > 0,
        "elevated": _is_elevated(),
        "cpu_name": r["name"],
        "temp_sensors": r["count"],
        "sample_temp": r["temp"],
        "sensor": r["sensor"],
        "sensor_id": r["sensor_id"],
        "selection": r["selection"],
        "all_temp_sensors": all_temps,
        "lhm_dir": lhm_dir,
        "pawnio_present": present,
        "pawnio_state": state,
    }
    print(json.dumps(out, indent=2))
    return 0 if r["count"] > 0 else 1


def _is_elevated():
    if sys.platform == "win32":
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    return False


def serve():
    """LHM init + start updater BEFORE bind/listen. Accept loop sends cache
    immediately after accept() - never blocks on Update()."""
    elevated = _is_elevated()
    computer, lhm_dir = init_lhm()
    if computer is None:
        _log("LHM init failed - cannot serve CPU temp")
        return 1

    # Startup logging (req 3): lhm_dir, file listing, PAWNIO state.
    listing = []
    try:
        listing = sorted(os.listdir(lhm_dir)) if lhm_dir else []
    except Exception:
        pass
    present, state = _pawnio_info()
    _log(f"startup: elevated={elevated} pid={os.getpid()} lhm_dir={lhm_dir}")
    _log(f"startup: lhm_files={listing}")
    _log(f"startup: PAWNIO_PRESENT={present} PAWNIO_STATE={state}")

    stop = threading.Event()
    updater = threading.Thread(target=_updater_loop, args=(computer, stop),
                               daemon=True)
    updater.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    except (AttributeError, OSError):
        pass
    try:
        sock.bind((HOST, PORT))
    except OSError as e:
        _log(f"port {PORT} already bound: {e}")
        stop.set()
        return 1
    sock.listen(5)
    _log(f"serving on {HOST}:{PORT} pid={os.getpid()}")

    try:
        while True:
            conn, _ = sock.accept()
            conn.settimeout(1.0)  # a silent client must not stall the accept loop
            try:
                # Send the CACHED value immediately - no LHM work on this thread.
                if conn.recv(64).strip() == b"GET":
                    resp = json.dumps({
                        "cpu_temp": _cache["temp"],
                        "cpu_name": _cache["name"],
                        "sensors": _cache["count"],
                        "sensor": _cache["sensor"],
                        "sensor_id": _cache["sensor_id"],
                        "selection": _cache["selection"],
                        "elevated": elevated,
                        "ts": _cache["ts"],
                    })
                    conn.sendall(resp.encode() + b"\n")
            except OSError:
                pass
            finally:
                conn.close()
    finally:
        stop.set()
        updater.join(timeout=2.0)
        try:
            computer.Close()
        except Exception:
            pass
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    return serve()


if __name__ == "__main__":
    sys.exit(main())
