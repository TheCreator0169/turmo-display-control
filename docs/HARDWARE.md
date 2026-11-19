# Hardware notes for TURMO / TURZX / Turing 3.5" USB IPS displays

## Short answer

The 3.5″ screen you have connected via USB is a **Turing Serial Rev-A** display driven by a CH552T MCU exposing a CDC ACM virtual COM port at 115200 baud. This repo treats the device as `turing-3.5` (libre-panel model name) and emits RGB565 pixel blocks over that serial interface.

## Model vs vendor naming

| Vendor label     | Compatible libre-panel model | Notes                                          |
|------------------|------------------------------|------------------------------------------------|
| Turing Smart     | `turing-3.5`                 | Original Arduino-shield style panels           |
| TURZX (3.5")     | `turing-3.5`                 | Chinese OEM branded; same CH552T board         |
| TURMO (your unit)| `turing-3.5` ✓ **confirmed** | VID=1A86 PID=5722 COM4 serial="TURMO_SCREEMV6"|

**Verification date:** 2026-11-12 (via `usb-discover.ps1`). The device matches `libre-panel` model `turing-3.5` by VID/PID; serial number differs but protocol is compatible per `models_for_usb()`.

**Do not assume TURMO = TURZX.** The branding may differ even when the underlying MCU/board does not. Only run vendor software if you must verify behavior; this project never installs or runs it.

## USB identity

Typical identification for the 3.5″ version:

```
VID = 1A86 (QinHeng Electronics / WCH)
PID = 5722
Class = CDC ACM (virtual serial)
Speed = Full-speed 12 Mbps
```

Windows will enumerate it under `USB\VID_1A86&PID_5722`. If your device has a different PID it may be a different size or revision — consult `docs/PANELS.md` in libre-panel before assuming compatibility.

## Known variants

- **Rev-A (this repo's target):** 3.5″ IPS, 480×320 landscape default, CH552T MCU. Used by most TURZX and Turing-branded panels sold on AliExpress/Temu.
- **Turzx-Mega / large boards:** Different form factor and likely different VID/PID; check against libre-panel's full model list (`libre-panel models`).
- **Older mini boards (2.13″ / 2.9″ ePaper):** Not relevant here — they use different controllers and protocols entirely.

If Windows shows a different PID (e.g. anything other than `5722`) or the device class isn't `CDC ACM`, stop and verify the hardware before continuing — sending Turing protocol frames to an incompatible controller will corrupt whatever is displayed.

## Protocol summary

Once detected, communication is straightforward ASCII+binary framing:

1. Open the COM port at 115200 8N1 with no flow control.
2. Send raw RGB565 pixel data in chunks sized to match the panel's line width (480 pixels × 2 bytes = 960 bytes per line).
3. Each frame is transmitted top-to-bottom; partial updates are supported but this repo's theme pipeline renders full frames for simplicity and reliability.

This repository relies on `libre_panel.devices.turing_rev_a` to handle framing, CRC and reconnection logic — callers do not emit raw frames themselves.

## Safe discovery checklist

Before connecting any script, confirm:

- [ ] Device shows up in Windows Device Manager with VID `1A86` and PID `5722`.
- [ ] COM port is assigned (look for `Silicon Labs CP210x` or `WCH USB-SERIAL CH552`).
- [ ] No proprietary TURMO driver or service is running (conflicts).
- [ ] In WSL: `lsusb` shows the device and permissions allow reading `/dev/ttyACM0` (or equivalent).

Run `scripts/usb-discover.ps1` on the host first; it prints exactly this information without touching the device.

## Licensing note

`libre-panel` is GPL-3.0. Any derivative works that link against it (including themes shipped as JSON) must remain open-source under compatible terms. See `libre-panel/LICENSE` in its source tree for details.
