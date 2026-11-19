#!/usr/bin/env python3
"""Regression tests for turmo_runtime.py — execute the REAL module against a mock serial port.

These tests actually import and call the runtime's functions (not just py_compile),
so missing globals like VID, wrong imports, or broken protocol framing are caught.

Run:  .venv/bin/python scripts/test_turmo_runtime.py
"""
import sys
import io
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
os.chdir(ROOT)

import turmo_runtime as rt

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL  {name}  {detail}")


# ── 1. Module constants exist with correct values ──────────────────────────────
print("== 1. Constants ==")
check("VID == 0x1A86", rt.VID == 0x1A86, f"got {rt.VID!r}")
check("PID == 0x5722", rt.PID == 0x5722, f"got {rt.PID!r}")
check("BAUD == 115200", rt.BAUD == 115200)
check("CMD_SCREEN_ON == 109", rt.CMD_SCREEN_ON == 109)
check("CMD_DISPLAY_BITMAP == 197", rt.CMD_DISPLAY_BITMAP == 197)
check("LANDSCAPE_SIZE == (480,320)", rt.LANDSCAPE_SIZE == (480, 320))
check("TURING_SIZE == (320,480)", rt.TURING_SIZE == (320, 480))

# ── 2. header() framing matches libre-panel reference ──────────────────────────
print("== 2. Protocol framing ==")
from libre_panel.devices.turing_rev_a import header as lp_header
for cmd in (rt.CMD_SCREEN_ON, rt.CMD_DISPLAY_BITMAP):
    for rect in [(0, 0, 0, 0), (0, 0, 479, 319), (10, 20, 300, 200)]:
        mine = rt.header(cmd, *rect)
        ref = lp_header(cmd, *rect)
        check(f"header({cmd}, {rect}) == libre-panel", mine == ref,
              f"mine={mine.hex()} ref={ref.hex()}")

# ── 3. RGB565 encoding matches libre-panel exactly ─────────────────────────────
print("== 3. RGB565 encoding ==")
from PIL import Image
from libre_panel.devices.serial_link import rgb565 as lp_rgb565
for color in [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (0, 0, 0), (128, 64, 32)]:
    img = Image.new("RGB", (8, 8), color)
    check(f"rgb565({color}) matches libre-panel",
          rt.rgb565(img, "little") == lp_rgb565(img, "little"))

# ── 4. find_turmo_port() auto-detection ────────────────────────────────────────
print("== 4. find_turmo_port() ==")
# Mock a serial port matching TURMO
class FakeInfo:
    def __init__(self, device, vid, pid):
        self.device = device
        self.vid = vid
        self.pid = pid
        self.description = "USB Serial Device"
        self.hwid = f"USB VID:PID={vid:04X}:{pid:04X}"
        self.serial_number = "TURMO_SCREEMV6"

turmo_port = FakeInfo("COM4", 0x1A86, 0x5722)
other_port = FakeInfo("COM3", 0x1A86, 0x7523)  # CH340, must NOT match

with patch("turmo_runtime.list_ports.comports", return_value=[other_port, turmo_port]):
    found = rt.find_turmo_port()
check("auto-detects COM4", found == "COM4", f"got {found!r}")

with patch("turmo_runtime.list_ports.comports", return_value=[other_port]):
    found = rt.find_turmo_port()
check("does NOT match CH340 (COM3)", found is None, f"got {found!r}")

# ── 5. TurmoDisplay protocol sequence against mock serial ──────────────────────
print("== 5. TurmoDisplay protocol sequence ==")
mock_ser = MagicMock()
with patch("turmo_runtime.serial.Serial", return_value=mock_ser):
    disp = rt.TurmoDisplay("COM4")
    disp.open()
    # open() should write CMD_SCREEN_ON once
    screen_on_calls = [c for c in mock_ser.write.call_args_list
                       if c[0][0] == rt.header(rt.CMD_SCREEN_ON)]
    check("open() sends CMD_SCREEN_ON", len(screen_on_calls) == 1,
          f"{len(screen_on_calls)} screen-on writes")

    # Send a bitmap (default is portrait: 320×480)
    img = Image.new("RGB", (320, 480), (10, 200, 30))
    ok = disp.send_bitmap(img)
    check("send_bitmap returns True", ok is True)
    # Verify header + pixel data were written
    writes = [c[0][0] for c in mock_ser.write.call_args_list]
    bitmap_header = rt.header(rt.CMD_DISPLAY_BITMAP, 0, 0, 319, 479)
    check("bitmap header sent", bitmap_header in writes)
    # Verify full pixel payload arrived (480*320*2 bytes)
    total_px = sum(len(w) for w in writes if isinstance(w, (bytes, bytearray)))
    check("full pixel payload (307200 bytes)", total_px >= 307200,
          f"{total_px} bytes")
    # rtscts=False passed to serial.Serial (check the patched factory's call)
    from unittest.mock import patch as _patch
    serial_mock = None
    # We need the serial.Serial mock itself; re-patch to capture it
    with _patch("turmo_runtime.serial.Serial", return_value=MagicMock()) as ser_factory:
        d2 = rt.TurmoDisplay("COM4")
        d2.open()
        check("rtscts=False", ser_factory.call_args.kwargs.get("rtscts") is False,
              f"{ser_factory.call_args}")

# ── 6. draw_test_pattern() produces correct image ──────────────────────────────
print("== 6. draw_test_pattern() ==")
img = rt.draw_test_pattern(str(ROOT / "previews" / "test-pattern-v2.png"))
check("480x320", img.size == (480, 320), f"got {img.size}")
check("RGB mode", img.mode == "RGB", f"got {img.mode}")
check("file written", (ROOT / "previews" / "test-pattern-v2.png").exists())

# ── 7. load_theme() resolves real themes ───────────────────────────────────────
print("== 7. load_theme() ==")
try:
    timg, tcfg = rt.load_theme("cyberpunk-neon")
    check("cyberpunk-neon loads", timg.size == (480, 320), f"got {timg.size}")
    check("theme config parsed", isinstance(tcfg, dict))
except Exception as e:
    check("cyberpunk-neon loads", False, f"{type(e).__name__}: {e}")

# ── 8. CLI --check runs without crashing (mocked ports) ────────────────────────
print("== 8. CLI smoke ==")
with patch("turmo_runtime.list_ports.comports", return_value=[turmo_port]):
    with patch.object(sys, "argv", ["turmo", "--check"]):
        rc = rt.main()
check("--check exits 0 with device present", rc == 0, f"rc={rc}")

# ── 9. CLI --test-image with mock serial ──────────────────────────────────────
print("== 9. CLI --test-image ==")
with patch("turmo_runtime.list_ports.comports", return_value=[turmo_port]):
    with patch("turmo_runtime.serial.Serial", return_value=MagicMock()):
        with patch.object(sys, "argv", ["turmo", "--test-image", "--port", "COM4"]):
            rc = rt.main()
check("--test-image exits 0", rc == 0, f"rc={rc}")

# ── 10. CLI --theme with mock serial ─────────────────────────────────────────
print("== 10. CLI --theme ==")
with patch("turmo_runtime.list_ports.comports", return_value=[turmo_port]):
    with patch("turmo_runtime.serial.Serial", return_value=MagicMock()):
        with patch.object(sys, "argv", ["turmo", "--theme", "cyberpunk-neon", "--once", "--port", "COM4"]):
            rc = rt.main()
check("--theme renders exit 0", rc == 0, f"rc={rc}")

# ── 11. CLI --theme with missing theme → error exit ───────────────────────────
print("== 11. CLI --theme missing theme ==")
with patch("turmo_runtime.list_ports.comports", return_value=[turmo_port]):
    with patch("turmo_runtime.serial.Serial", return_value=MagicMock()):
        with patch.object(sys, "argv", ["turmo", "--theme", "does-not-exist", "--once", "--port", "COM4"]):
            rc = rt.main()
check("--theme missing exits 1", rc == 1, f"rc={rc}")

print(f"\n{'='*50}")
print(f"RESULT: {PASS} passed, {FAIL} failed")
if FAILURES:
    print("FAILED:", ", ".join(FAILURES))
    sys.exit(1)
print("ALL TESTS PASSED")
