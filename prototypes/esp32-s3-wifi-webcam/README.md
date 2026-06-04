# ESP32-S3 Wi-Fi Webcam Prototype

Isolated firmware for Story 005. This is a prototype utility for using the Freenove ESP32-S3 WROOM camera board as a projector-mounted Wi-Fi camera source. It is not final product firmware.

## Local Secrets

Create `include/secrets.h` locally. It is gitignored.

```cpp
#pragma once

#define WIFI_SSID "your-network"
#define WIFI_PASSWORD "your-password"
```

If Wi-Fi credentials are empty or connection fails, the board starts a fallback access point named `RPG-ESP32S3-CAM`.

For the current local proof, the board joined station Wi-Fi at
`http://192.168.86.45` and exposed the endpoints below. That address comes from
DHCP and may change after rebooting the board or network.

## Endpoints

- `/` - simple preview page
- `/capture` - single VGA JPEG still
- `/capture?size=max` - highest known still size for the detected sensor
- `/capture?size=uxga` - 1600 x 1200 still, useful for OV2640 boards
- `/capture?size=qxga` - 2048 x 1536 still, useful for OV3660 boards
- `/stream` - short diagnostic MJPEG response
- `/status` - JSON status with sensor PID/name and default/current/max frame size
- `/preset?name=bright-mat` - low-light tabletop tuning preset for grid capture
- `/preset?name=default` - restore the prototype default sensor tuning
- `/control?var=brightness&value=2` - set one sensor control directly

The firmware prints the camera URLs to serial once networking starts.

The default prototype capture size is VGA, 640 x 480. This keeps the preview
and workbench path usable. For calibration stills that do not need to be live,
request `size=max` or a named high-resolution frame size and expect a slower
single response. After a high-resolution still, the firmware restores the camera
to VGA so the preview remains responsive.

On the current board, `/status` reports an OV2640 sensor with UXGA max stills.
The firmware initializes PSRAM frame buffers at UXGA, then downshifts the normal
capture path to VGA. This is required because raising a camera initialized at
VGA can leave the JPEG payload at 640 x 480 even when framebuffer metadata says
1600 x 1200. The `/capture` response validates JPEG payload dimensions before
returning a frame.

The `bright-mat` preset is meant for the current projector-mounted proof rig
when the ESP32 frame is too dark for passive grid detection. It raises
brightness, enables secondary exposure, raises auto-exposure level, raises auto
gain, and lowers JPEG quantization. It is a diagnostic preset, not a final
image-quality decision. On the current OV2640 path, two optional controls are
reported as unsupported while the core preset settings still apply.

## Workbench Camera Config

Create `network-camera.local.json` when the board has a DHCP address. It is
gitignored because the address is local-session state.

```json
{
  "cameras": [
    {
      "id": "esp32s3-direct",
      "label": "ESP32-S3 Wi-Fi Camera",
      "baseUrl": "http://192.168.86.45",
      "capturePath": "/capture",
      "detectionCapturePath": "/capture?size=max",
      "rotationDegrees": 270
    }
  ]
}
```

The local Vite gateway reads that file for `/__network-cameras` and proxies
still captures through `/__network-camera-capture?id=esp32s3-direct`.
`capturePath` is used for the live preview canvas. `detectionCapturePath` is
used only when the workbench captures a calibration/detection still, so the
preview can stay responsive at VGA while detector input can use `size=max`.
Use `rotationDegrees` when the board is mounted sideways. Supported values are
`0`, `90`, `180`, and `270`; the workbench rotates the canvas stream before
capturing or running detection, leaving the detector code itself unchanged.

## PlatformIO

```bash
pio run
pio run -t upload --upload-port /dev/cu.wchusbserial54E20247261
pio device monitor -p /dev/cu.wchusbserial54E20247261 -b 115200
```

The native ESP32-S3 USB/JTAG connector is the currently verified upload path:

```bash
pio run -e freenove_esp32_s3_wroom_jtag -t upload
pio device monitor -p /dev/cu.usbmodem101 -b 115200
```

After a successful native USB/JTAG flash, the board's USB CDC serial output
prints the firmware banner and endpoint URLs.

The folder also includes `esptool.cfg`, which increases esptool timeouts and
write retries for the current CH343/macOS transport issue.

## USB Port Notes

The local Freenove notes for this exact board say the working Mac port was
`/dev/cu.wchusbserial54E20247261` after the WCH CH343 driver was installed and
allowed in macOS Privacy & Security.

If macOS only exposes `/dev/cu.usbmodem54E20247261`, `esptool` can identify the
ESP32-S3 but upload may fail while writing the flasher stub. Recover the WCH
driver binding first, then retry the upload on the `wchusbserial` port.

Current local evidence points to Apple CDC claiming the CH343 serial interface
as `usbmodem` while the WCH DriverKit extension is present but not winning the
match. Official WCH metadata lists `CH34XSER_MAC.ZIP` / `CH341SER_MAC.ZIP`
version `2.0`, uploaded `2025-12-01`, with CH343 and Big Sur+ support. Install
or reactivate the current WCH driver from WCH, approve it in Privacy & Security,
unplug/replug the board, then confirm:

```bash
ls /dev/cu.wchusbserial54E20247261
```

Avoid repeated write attempts on `/dev/cu.usbmodem54E20247261` unless
deliberately testing the Apple CDC path. No-stub reads work there, but local
stub upload and flash writes fail.

If WCH version `2.0` is installed and enabled but only `usbmodem` appears, try
the other USB-C connector on the Freenove board, preferably after a Mac restart.
The board has two USB-C connectors; the CH343 connector currently enumerates as
VID `0x1a86`, PID `0x55d3`, product `USB Single Serial`.

The alternate/native USB-C connector enumerates as Espressif VID `0x303a`, PID
`0x1001`, product `USB JTAG_serial debug unit`. PlatformIO upload works through
that connector with `upload_protocol = esp-builtin`; after flashing, USB CDC
serial appears as `/dev/cu.usbmodem101` in the current local session.

Current native USB/JTAG evidence:

- `pio run -e freenove_esp32_s3_wroom_jtag -t upload` programs and verifies the
  firmware successfully.
- USB CDC serial shows the firmware boot banner, Wi-Fi attempt, fallback AP, and
  endpoint URLs.
- The board starts fallback AP mode at `http://192.168.4.1/` when the configured
  station SSID is not visible from the Mac.

If using fallback AP mode from the Mac, remember that joining
`RPG-ESP32S3-CAM` with password `projector` will take the Mac off the home Wi-Fi
unless another active network adapter is providing the default route.

Current local failure signature on the Apple CDC path:

```bash
# Read/probe succeeds:
esptool --no-stub --chip esp32s3 --port /dev/cu.usbmodem54E20247261 flash-id

# Stub upload fails:
pio run -t upload --upload-port /dev/cu.usbmodem54E20247261

# No-stub write erases, then fails on first write block:
esptool --no-stub --chip esp32s3 --port /dev/cu.usbmodem54E20247261 write-flash ...
```
