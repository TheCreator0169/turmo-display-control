"""Self-check for CPU temperature sensor selection and the unavailable path.
No LibreHardwareMonitor or admin needed: LHM objects are faked.
Run: .venv-win/Scripts/python.exe scripts/test_cpu_temp_selection.py"""
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cpu_temp_helper as h  # noqa: E402


class _Named:
    def __init__(self, v):
        self.v = v

    def __str__(self):
        return self.v


class FakeSensor:
    def __init__(self, kind, name, ident, value):
        self.SensorType = _Named(kind)
        self.Name = name
        self.Identifier = ident
        self.Value = value


class FakeHw:
    def __init__(self, kind, name, sensors, subs=()):
        self.HardwareType = _Named(kind)
        self.Name = name
        self.Sensors = sensors
        self.SubHardware = list(subs)

    def Update(self):
        pass


class FakeComputer:
    def __init__(self, hw):
        self.Hardware = hw


def cpu(*sensors):
    return FakeComputer([FakeHw("Cpu", "Test CPU", list(sensors))])


fails = []


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        fails.append(label)


# 1. A real package sensor wins over a higher single-core reading.
r = h.harvest_cpu_temp(cpu(
    FakeSensor("Temperature", "Core #1", "/cpu/0/temperature/1", 80.0),
    FakeSensor("Temperature", "CPU Package", "/cpu/0/temperature/0", 57.0),
    FakeSensor("Load", "CPU Total", "/cpu/0/load/0", 99.0),  # not a temperature
))
check("package sensor preferred", r["selection"] == "package" and r["temp"] == 57.0
      and r["sensor"] == "CPU Package" and r["sensor_id"] == "/cpu/0/temperature/0")

# 2. AMD name is also recognised.
r = h.harvest_cpu_temp(cpu(FakeSensor("Temperature", "Core (Tctl/Tdie)", "/amd/t", 61.5)))
check("AMD Tctl/Tdie recognised", r["selection"] == "package" and r["temp"] == 61.5)

# 3. No package sensor: falls back to max, and says so.
r = h.harvest_cpu_temp(cpu(
    FakeSensor("Temperature", "Core #1", "/cpu/0/temperature/1", 50.0),
    FakeSensor("Temperature", "Core #2", "/cpu/0/temperature/2", 53.0),
))
check("fallback labelled max", r["selection"] == "max" and r["temp"] == 53.0
      and r["sensor"] == "Core #2")

# 4. No temperature at all: no value is invented.
r = h.harvest_cpu_temp(cpu(FakeSensor("Load", "CPU Total", "/cpu/0/load/0", 10.0)))
check("no sensor -> None, not a guess", r["temp"] is None and r["selection"] == "none")

# 5. Unavailable helper: the GUI/Monitor reader returns {} and never raises.
import turmo_runtime as rt  # noqa: E402


def refused(*a, **k):
    raise ConnectionRefusedError("helper not running")


_real = socket.create_connection
socket.create_connection = refused
try:
    check("helper down -> empty reading, no exception", rt.read_cpu_temperature() == {})
finally:
    socket.create_connection = _real

print("RESULT:", "ALL PASSED" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
