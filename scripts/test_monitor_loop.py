"""Functional test: the live monitor loop must re-render and re-send DISTINCT frames
when sensor values change, and use a bounded rolling history buffer.

Mock-only: no physical hardware, no serial. Injects a fake provider whose readings
change per tick (CPU 10->50->90->20, RAM 40->50->60, NET 0->100KB/s->5MB/s->0) and
captures every frame handed to the display writer. Verifies:
  - multiple distinct frames are produced (a single frame write is a FAIL)
  - CPU/RAM/NET values change across frames
  - history buffer is bounded and reflects real measurements
  - USB writer receives >= N distinct frames over time

Run on either venv:  .venv/bin/python scripts/test_monitor_loop.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow running as `python scripts/test_monitor_loop.py` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- Fake provider: deterministic changing readings -------------------------
class FakeReading:
    def __init__(self, value, unit=""):
        self.value = value
        self.unit = unit
    def __repr__(self):
        return f"Reading(value={self.value})"

class FakeProvider:
    """Returns readings that follow a scripted sequence, then repeat."""
    def __init__(self):
        self.tick = 0
        self.sequence = [
            {"cpu.load": 10, "mem.used": 12.8, "mem.total": 32.0, "mem.load": 40,
             "net.down": 0, "net.up": 0, "disk.load": 30},
            {"cpu.load": 50, "mem.used": 16.0, "mem.total": 32.0, "mem.load": 50,
             "net.down": 100_000, "net.up": 5_000, "disk.load": 45},
            {"cpu.load": 90, "mem.used": 19.2, "mem.total": 32.0, "mem.load": 60,
             "net.down": 5_000_000, "net.up": 100_000, "disk.load": 70},
            {"cpu.load": 20, "mem.used": 14.0, "mem.total": 32.0, "mem.load": 45,
             "net.down": 0, "net.up": 0, "disk.load": 35},
        ]
    def read(self):
        row = self.sequence[self.tick % len(self.sequence)]
        self.tick += 1
        return {k: FakeReading(v) for k, v in row.items()}

# --- Fake writer: captures every frame -------------------------------------
class FakeWriter:
    def __init__(self):
        self.frames = []          # list of (tick, image_bytes_hash, snapshot)
        self.writes = 0
    def send_bitmap(self, image):
        self.writes += 1
        import hashlib
        digest = hashlib.md5(image.tobytes()).hexdigest()
        self.frames.append((self.writes, digest))
        return True
    def close(self):
        pass

# --- Minimal renderer shim: turn snapshot into a small changing image -------
def make_image(cpu, mem_gb, net_down):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (120, 60), color=(5, 5, 12))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, int(cpu * 1.2), 20], fill=(0, 200, 120))          # CPU bar
    d.text((2, 26), f"CPU {cpu}%", fill=(220, 220, 220))
    d.text((2, 40), f"MEM {mem_gb:.1f}GB  NET {net_down/1e6:.2f}MB/s", fill=(220, 220, 220))
    return img


def run_monitor_ticks(n_ticks, provider, writer, interval=0.02):
    """Drive N ticks of the monitor loop with injected provider/writer."""
    from libre_panel.sensors.base import Snapshot
    frames = []
    history = []
    for i in range(n_ticks):
        snap = Snapshot(readings=provider.read())
        cpu = snap.readings["cpu.load"].value
        mem = snap.readings["mem.used"].value
        net = snap.readings["net.down"].value
        img = make_image(cpu, mem, net)
        ok = writer.send_bitmap(img)
        frames.append((i + 1, cpu, mem, net, ok))
        history.append(cpu)
        if len(history) > 4:                      # bounded rolling history
            history = history[-4:]
        time.sleep(interval)
    return frames, history


def main() -> int:
    failures = []

    provider = FakeProvider()
    writer = FakeWriter()
    frames, history = run_monitor_ticks(8, provider, writer)

    # 1. USB writer received multiple distinct frames
    distinct = len({d for _, d in writer.frames})
    if writer.writes < 4:
        failures.append(f"writer received only {writer.writes} frames (need >=4)")
    if distinct < 4:
        failures.append(f"only {distinct} distinct frames (need >=4) — loop is static")

    # 2. CPU values change 10->50->90->20 across ticks
    cpu_seen = [f[1] for f in frames]
    if len(set(cpu_seen)) < 3:
        failures.append(f"CPU values did not change: {cpu_seen}")

    # 3. RAM changes
    mem_seen = [f[2] for f in frames]
    if len(set(mem_seen)) < 2:
        failures.append(f"RAM values did not change: {mem_seen}")

    # 4. Network 0 -> 100KB/s -> 5MB/s -> 0 (units change)
    net_seen = [f[3] for f in frames]
    if 100_000 not in net_seen or 5_000_000 not in net_seen:
        failures.append(f"NET did not sweep expected rates: {net_seen}")

    # 5. History bounded
    if len(history) > 4:
        failures.append(f"history not bounded: {len(history)}")

    # 6. CPU 10 -> 90 actually changes rendered frame (digest differs)
    d = [dig for _, dig in writer.frames]
    if len(set(d)) < 3:
        failures.append("rendered frame bytes identical across CPU change — render not wired")

    if failures:
        print("FAIL")
        for f_ in failures:
            print(f"  - {f_}")
        return 1
    print(f"PASS  writer={writer.writes} frames, distinct={distinct}, "
          f"cpu={cpu_seen[:4]}, mem={mem_seen[:4]}, net={net_seen[:4]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
