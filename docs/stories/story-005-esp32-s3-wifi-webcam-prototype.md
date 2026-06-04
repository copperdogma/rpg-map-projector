---
{
  "title": "ESP32-S3 Wi-Fi Webcam Prototype",
  "status": "Done",
  "priority": "High",
  "origin": "The phone-as-camera path is ergonomically poor and not representative of the likely fixed camera. An available ESP32-S3 WROOM camera board can remove the phone from the loop and provide projector-mounted fixed-camera evidence.",
  "ideal_refs": ["docs/ideal.md"],
  "spec_refs": ["spec:2.1", "spec:2.2", "spec:3.1", "spec:6.1"],
  "depends_on": ["001"],
  "category_refs": ["spec:2", "spec:3", "spec:6"],
  "compromise_refs": ["B2", "B3", "B7"]
}
---

# Story 005: ESP32-S3 Wi-Fi Webcam Prototype

## Goal

Bring up the ESP32-S3 WROOM camera board as a projector-mountable Wi-Fi camera source for the current laptop gateway, then make that source selectable from the Calibration Projection Spike workbench.

The prototype is successful when the workbench can use the ESP32-S3 camera path to capture a recognizable live image, with the board currently aimed at the credenza, without relying on the user's phone.

## Background

Scout 004 rejected classic ESP32-CAM as a Mac USB webcam and gateway candidate, but the actual available board is ESP32-S3 WROOM with USB attached. That makes a Wi-Fi camera firmware spike practical.

This story is not choosing final camera hardware. It is a prototyping utility so the physical projection work can keep moving without occupying the user's phone.

## Scope

Build the smallest isolated utility that can:

- identify and flash the attached ESP32-S3 WROOM camera board,
- host a Wi-Fi camera endpoint on the local network,
- expose at least a still JPEG endpoint and preferably an MJPEG stream endpoint,
- keep firmware and board-specific code in a separate prototype folder,
- let the laptop gateway/workbench consume that network camera path,
- surface the ESP32-S3 camera as a selectable camera option in the Calibration Projection Spike page,
- capture a usable frame from the selected ESP32-S3 source through the existing workbench flow.

## Acceptance Criteria

- The active worktree uses a new story number that does not collide with existing stories.
- ESP32-S3 firmware lives in an isolated prototype folder rather than the main app source tree.
- The board can be flashed from this Mac over the detected USB serial port.
- The board joins a local Wi-Fi network or fallback access point and exposes its camera address in serial output.
- A browser or command-line request from the Mac can fetch a recognizable still frame from the board.
- The Calibration Projection Spike page shows the ESP32-S3 camera in the camera dropdown.
- Selecting the ESP32-S3 camera and capturing from the workbench produces a recognizable image from the board's current view.
- Story evidence records board identity, USB port, firmware folder, network endpoint, capture path, and any pin-map or image-quality caveats.

## Non-Goals

- Choosing final camera hardware.
- Making the ESP32-S3 a gateway/minicomputer.
- Replacing the HDMI projector/laptop gateway topology.
- Shipping ESP32 firmware as part of the product runtime.
- Solving active projector-camera calibration.
- Polishing camera setup UI beyond what is needed for this prototype.

## Implementation Plan

- [x] Confirm story numbering and create Story 005.
- [x] Identify the attached USB serial device and ESP32-S3 chip facts.
- [x] Identify or configure the camera pin map for this board.
- [x] Add isolated ESP32-S3 Wi-Fi camera firmware under a prototype folder.
- [x] Flash the firmware from the Mac.
- [x] Verify the board exposes a still or stream endpoint with a recognizable image.
- [x] Add a laptop gateway/workbench ingest path so the ESP32-S3 source appears in the Calibration Projection Spike camera dropdown.
- [x] Capture and verify an ESP32-S3 frame through the workbench.
- [x] Record validation evidence and rough image-quality caveats.
- [x] Add a follow-up high-resolution still-capture path for calibration photos while keeping VGA as the responsive preview/default path.
- [x] Add follow-up sensor tuning endpoints for low-light calibration stills.
- [x] Reflash the ESP32-S3 board and verify `/status`, default `/capture`, `/capture?size=max`, `/preset?name=bright-mat`, and `/preset?name=default` on the physical device.

## Current Evidence

- Existing authored stories are `001` through `004`; this story uses `005`.
- The attached serial device is `/dev/cu.usbmodem54E20247261`.
- `esptool.py --chip esp32s3 --port /dev/cu.usbmodem54E20247261 chip_id` connected to an `ESP32-S3 (QFN56)`, revision `v0.1`, with Wi-Fi, BT 5 LE, dual core plus LP core, 240 MHz, embedded PSRAM 8 MB, 40 MHz crystal, and MAC `34:85:18:a6:4f:a0`.
- The first esptool probe connected but failed while uploading the stub flasher with `Failed to write to target RAM (result was 0107: Checksum error)`, so no-stub flashing/readback may be needed.
- PlatformIO is installed locally as `pio`, version `6.1.18`.
- Parent-project evidence from `/Users/cam/Documents/Arduino/libraries/Freenove_ESP32_S3_WROOM_Board-main/CAM NOTES.txt` says this exact board previously worked on `/dev/cu.wchusbserial54E20247261` after allowing the WCH driver in Privacy & Security.
- The Freenove CH343 Mac notes say Mac users should install the latest CH343 driver from WCH because older versions may not be suitable.
- The current Mac only exposes `/dev/cu.usbmodem54E20247261`, not `/dev/cu.wchusbserial54E20247261`, even though the WCH system extension is installed and active.
- The isolated firmware uses the Freenove `CAMERA_MODEL_ESP32S3_EYE` pin map: XCLK 15, SIOD 4, SIOC 5, Y2 11, Y3 9, Y4 8, Y5 10, Y6 12, Y7 18, Y8 17, Y9 16, VSYNC 6, HREF 7, PCLK 13.
- `prototypes/esp32-s3-wifi-webcam` contains PlatformIO firmware with `/capture`, `/stream`, `/status`, station Wi-Fi, fallback AP, and ignored local Wi-Fi secrets.
- The Vite dev server now exposes configured network cameras through `/__network-cameras` and proxies still captures through `/__network-camera-capture`.
- The Calibration Projection Spike camera selector includes `ESP32-S3 Wi-Fi Camera` network entries alongside browser webcam devices.
- A focused Playwright test covers a mocked ESP32-S3 network camera source through selector, start, capture, evidence display, and persisted camera evidence.
- `pio run` succeeds in `prototypes/esp32-s3-wifi-webcam`.
- `npm run build`, `npx playwright test tests/e2e/calibration-workbench.spec.ts -g "network cameras|selected live camera"`, `make methodology-compile`, and `make methodology-check` pass after the app/story updates.
- A fresh PlatformIO upload attempt on `/dev/cu.usbmodem54E20247261` still identifies the ESP32-S3 and MAC `34:85:18:a6:4f:a0`, then fails at `Uploading stub...` with `Failed to write to target RAM (result was 01070000: Operation timed out)`.
- A safe 115200-baud stub probe on `/dev/cu.usbmodem54E20247261` fails with the same `01070000: Operation timed out` result, while `esptool.py --no-stub ... flash_id` succeeds and reports flash manufacturer `c8`, device `4017`, 8 MB flash, quad mode, and 3.3 V.
- macOS currently publishes the board's serial interface as `AppleUSBACMData` with `/dev/cu.usbmodem54E20247261`, even though the installed WCH DriverKit extension has a matching CH343 personality for VID `0x1a86`, PID `0x55d3`, interface `1`.
- The installed WCH helper/driver is 2022-era (`CH34xVCPDriver.app` `1.8`, DriverKit extension `1.0`). Official WCH metadata lists `CH34XSER_MAC.ZIP` / `CH341SER_MAC.ZIP` version `2.0`, uploaded `2025-12-01`, supporting CH343-class devices on Big Sur and newer.
- A DTR/RTS reset toggle and port rescan did not cause `/dev/cu.wchusbserial54E20247261` to appear.
- Direct CLI download of the current WCH ZIP through the official API returned a refresh/retry JSON response instead of the package, so updating or re-approving the WCH driver still needs browser/System Settings/admin interaction outside this shell.
- After user-side WCH installation/approval, `pkgutil` reports `cn.wch.pkg.CH34xVCPDriver` version `2.0`, `/Applications/CH34xVCPDriver.app` reports `CFBundleShortVersionString` `2.0`, and `systemextensionsctl` reports `cn.wch.CH34xVCPDriver (1.0/1)` activated and enabled.
- Even with WCH version `2.0` installed and enabled, macOS still publishes only `/dev/cu.usbmodem54E20247261`; no `/dev/cu.wchusbserial54E20247261` appears.
- `ioreg` shows Apple CDC still owns the interfaces: `AppleUSBACMControl` with `IOProbeScore` `60000` and `AppleUSBACMData` with `IOProbeScore` `49998`, while the USB device is `USB Single Serial`, VID `0x1a86`, PID `0x55d3`, serial `54E2024726`.
- Added prototype-local `esptool.cfg` with longer timeouts and write retries per Espressif's documented mitigation path for `0107` serial write instability; the PlatformIO stub upload still fails with `01070000: Operation timed out`.
- A temporary esptool `5.1.0` environment can identify the board and read flash metadata, but the stub upload still fails with `0107` and no-stub writes erase the first block then fail on write sequence `0` with `0105`.
- `esptool get_security_info` and `espefuse summary` show secure boot disabled, flash encryption disabled, download mode not disabled, USB serial/JTAG download mode not disabled, and flash voltage at 3.3 V.
- Freenove's board image/pinout shows two USB-C connectors. A one-minute port watcher did not observe a new serial node during the first alternate-port attempt, so the next physical attempt should deliberately use the other connector and/or a restart after WCH driver approval.
- Moving the cable to the board's alternate/native USB-C connector exposes Espressif `USB JTAG_serial debug unit`, VID `0x303a`, PID `0x1001`, serial `34:85:18:A6:4F:A0`, and `/dev/cu.usbmodem101`.
- `pio run -e freenove_esp32_s3_wroom_jtag -t upload` successfully programs and verifies the firmware through PlatformIO's `esp-builtin` upload path.
- USB CDC serial output on `/dev/cu.usbmodem101` now shows the firmware banner, which confirms the flashed application is running.
- The firmware reaches `Joining Wi-Fi` only after `esp_camera_init` succeeds, so the Freenove ESP32S3_EYE pin map is at least passing camera initialization on this board.
- Before the local credentials were corrected, serial output showed fallback AP mode at `http://192.168.4.1` because the compiled station SSID was not visible from the Mac.
- After updating ignored `include/secrets.h` and reflashing through native USB/JTAG, the board joined station Wi-Fi at `http://192.168.86.45` and reported `/capture`, `/stream`, and `/status`.
- `curl http://192.168.86.45/status` returned `{"name":"rpg-esp32s3-webcam","mode":"station","ip":"192.168.86.45","rssi":-36,"psram":true,...}`.
- Direct `/capture` returns recognizable room/credenza JPEGs. The prototype now uses `FRAMESIZE_VGA` so current frames are 640 x 480 JPEGs around 13-14 KB.
- Local firmware now exposes sensor PID/name plus default/current/max frame-size metadata through `/status`, and supports high-resolution one-shot stills through `/capture?size=max`, `uxga`, or `qxga` before restoring VGA for preview responsiveness.
- The flashed board reports sensor PID `0x26`, `OV2640`, PSRAM available, default/current VGA `640 x 480`, and max UXGA `1600 x 1200`.
- Physical-device validation used the USB/JTAG connection only for flashing; all image captures were fetched over Wi-Fi from `http://192.168.86.45`.
- Wi-Fi `/capture` returns a VGA JPEG with actual payload dimensions `640 x 480`.
- Wi-Fi `/capture?size=max` returns an actual UXGA JPEG with payload dimensions `1600 x 1200` after initializing PSRAM frame buffers at UXGA and then downshifting normal preview/capture back to VGA.
- After the max still capture, `/status` and a follow-up Wi-Fi `/capture` confirmed the camera returned to VGA.
- Local firmware source now exposes sensor tuning state through `/status`, direct control writes through `/control?var=<name>&value=<number>`, and presets through `/preset?name=bright-mat` and `/preset?name=default`. The bright-mat preset raises exposure/gain/brightness-oriented settings for the current dark projector-mounted proof rig.
- Physical preset validation over Wi-Fi shows `/preset?name=bright-mat` and `/preset?name=default` both return HTTP 200 with `ok:true`; each reports two optional unsupported controls on this OV2640 path while applying the core quality, brightness, contrast, exposure, gain, white-balance, flip, and lens settings.
- The first SVGA capture implementation sometimes closed before the full JPEG transferred. The firmware now writes `/capture` in checked TCP chunks and closes the connection after the full response.
- `prototypes/esp32-s3-wifi-webcam/network-camera.local.json` points the local workbench at `http://192.168.86.45`; the file is gitignored because the board's DHCP address is local-session state.
- The Vite proxy `/__network-camera-capture?id=esp32s3-direct` returned a 640 x 480 JPEG from the ESP32-S3 camera.
- Browser-level workbench validation selected `ESP32-S3 Wi-Fi Camera`, started a 640 x 480 network camera stream, captured `camera-frame-2026-06-03T17-50-55-769Z.jpg`, rendered the recognizable camera image, and recorded session evidence.
- Detection failed honestly on the current credenza view with `No reliable grid found`, which is expected because the board is not aimed at a grid. The frame remains loaded for manual seed fallback.
- Image caveats: current firmware flips vertically, the board is physically sideways in the test scene, low light produces noisy/dark frames, and the ESP32 single-frame path is slow enough that the dev proxy uses a 20 second timeout.
- After disconnecting the ESP32-S3 from the laptop and powering it from a separate USB-C power source, no `/dev/cu.usbmodem*` serial device was present, but `http://192.168.86.45/status`, direct `/capture`, the Vite proxy, and the full workbench capture flow still worked over Wi-Fi.
- Final validation flashed a firmware fix that keeps the root preview on repeated `/capture` requests and limits `/stream` to a short diagnostic response. With the board power-only, direct `/capture`, proxy capture, diagnostic `/stream` followed by `/status`, and full workbench capture all succeeded over Wi-Fi.

## Work Log

- 20260603-0000 - Created Story 005 after confirming existing story numbers stop at `004`.
- 20260603-0001 - Confirmed the Mac sees `/dev/cu.usbmodem54E20247261` and esptool can identify the attached ESP32-S3 with 8 MB PSRAM.
- 20260603-0002 - Checked `/Users/cam/Documents/Projects/death-fortune-teller`, `/Users/cam/Documents/Projects/TwoSkulls`, and the local Freenove ESP32-S3 WROOM bundle. The useful match was the Freenove CH343 driver note and exact prior port `/dev/cu.wchusbserial54E20247261`; Death Fortune Teller mostly confirmed the local PlatformIO ESP32 pattern and 460800 upload speed.
- 20260603-0003 - Added isolated PlatformIO firmware under `prototypes/esp32-s3-wifi-webcam` using Freenove's ESP32S3_EYE camera pin map.
- 20260603-0004 - Added Vite network-camera discovery/proxy endpoints and wired the Calibration Projection Spike camera dropdown to network camera pseudo-devices.
- 20260603-0005 - Verified the network-camera workbench path with mocked `/__network-cameras` and `/__network-camera-capture` Playwright coverage. Physical flashing is still pending because the board is exposed as `usbmodem` instead of the previously working `wchusbserial` port, and every flash write attempt fails after successful read/probe operations.
- 20260603-0006 - Rebuilt firmware and app, reran focused Playwright coverage, refreshed methodology graph/stories, and confirmed methodology check passes. Retried upload on `/dev/cu.usbmodem54E20247261`; it still fails while uploading the flasher stub, so next physical action is recovering the WCH/CH343 `wchusbserial` port before another flash attempt.
- 20260603-0007 - Inspected macOS driver binding and confirmed Apple CDC ACM is publishing `usbmodem` on interface 1 while the WCH DriverKit extension has a matching CH343 personality. A safe 115200 stub probe still fails, no-stub `flash_id` succeeds, and DTR/RTS reset did not change the device node.
- 20260603-0008 - Queried official WCH metadata showing macOS driver version `2.0`, uploaded `2025-12-01`, for CH343-class devices. The local installed WCH driver/helper remains 2022-era and likely needs user-approved update/reactivation before flashing.
- 20260603-0009 - Confirmed user-side WCH install upgraded the package and helper app to version `2.0`, with the DriverKit extension activated and enabled. The board still enumerates as Apple CDC `/dev/cu.usbmodem54E20247261`, not WCH `/dev/cu.wchusbserial54E20247261`.
- 20260603-0010 - Added prototype-local esptool timing configuration and tested PlatformIO upload, no-stub writes, esptool `5.1.0`, minimal bootloader-only writes, `usb_reset`, and security/efuse reads. Reads and erase work; all stub or flash write paths fail through the current Apple CDC serial node.
- 20260603-0011 - Retried after moving the cable to the board's alternate/native USB-C connector. macOS exposed Espressif USB/JTAG plus `/dev/cu.usbmodem101`, and PlatformIO `esp-builtin` upload succeeded.
- 20260603-0012 - Read USB CDC serial after flashing. The firmware boots, camera initialization passes, station Wi-Fi fails because the compiled SSID is not visible from the Mac, and fallback AP mode starts at `http://192.168.4.1`; capture verification is blocked until the Mac joins that AP or the firmware is reflashed with visible network credentials.
- 20260603-0013 - Replaced local ignored Wi-Fi placeholders, reflashed through native USB/JTAG, and confirmed station mode at `http://192.168.86.45` with `/status`, `/capture`, `/stream`, and PSRAM available.
- 20260603-0014 - Fixed incomplete `/capture` responses by chunking the JPEG body, then downshifted the prototype still size to VGA for usable workbench latency.
- 20260603-0015 - Added ignored `network-camera.local.json` for the current DHCP address, widened the dev proxy timeout to 20 seconds, and verified `/__network-camera-capture?id=esp32s3-direct` returns a valid 640 x 480 JPEG.
- 20260603-0016 - Verified the full Calibration Projection Spike workbench path in Playwright: select ESP32-S3 camera, start 640 x 480 network stream, capture a recognizable board frame, preserve it in the preview, and record session evidence while detection fails safely on the non-grid scene.
- 20260603-0017 - Verified Wi-Fi-only operation after the board was disconnected from the laptop and powered by a separate USB-C power source. Direct status/capture, Vite proxy capture, and the browser workbench path still succeeded without any USB serial device attached.
- 20260603-0018 - Validation found that an unlimited direct `/stream` response could monopolize the ESP32 web server. Replaced the root preview with repeated `/capture` requests, capped `/stream` to three chunked diagnostic frames, reflashed, and revalidated power-only operation with no USB serial device attached.
- 20260603-0019 - Added the high-resolution still-capture follow-up requested after the calibration workflow shifted from live streaming toward occasional mat/grid photos. `/status` now reports sensor PID/name and frame-size metadata; `/capture?size=max` chooses the detected sensor's known maximum still size, while the default capture path stays VGA. `pio run -e freenove_esp32_s3_wroom_jtag` and `pio run` both pass locally; physical flash and endpoint verification are pending until the board is plugged into the native USB/JTAG connector.
- 20260603-0020 - Added low-light sensor tuning firmware endpoints and workbench integration hooks. `/preset?name=bright-mat` applies a tabletop low-light preset, `/preset?name=default` restores prototype defaults, and `/control` can set individual ESP32 camera sensor parameters. The workbench config now separates VGA preview `capturePath` from high-resolution `detectionCapturePath` so detector stills can use `/capture?size=max` without slowing the live preview.
- 20260603-0021 - Flashed the native USB/JTAG-connected board on `/dev/cu.usbmodem101` and validated image paths only over Wi-Fi. `/status` reported OV2640 PID `0x26`, default/current VGA, and max UXGA. Initial validation caught that framebuffer metadata could claim UXGA while the JPEG payload remained VGA, so the firmware now parses JPEG dimensions before accepting/reporting a frame. The final flashed build initializes PSRAM frame buffers at UXGA, restores the normal path to VGA, returns a real `1600 x 1200` JPEG from `/capture?size=max`, returns to `640 x 480` afterward, and successfully applies/restores the bright-mat/default presets with only optional control fallbacks.
