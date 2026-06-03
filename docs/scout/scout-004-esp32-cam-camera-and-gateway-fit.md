# Scout 004 - ESP32-CAM Camera And Gateway Fit

**Source / Question:** Can an ESP32-CAM replace the phone camera, appear as a USB webcam on the MacBook, or act as the prototype gateway/minicomputer?
**Scouted:** 2026-06-03
**Scope:** Classic Ai-Thinker-style ESP32-CAM boards, ESP32-S2/S3 USB UVC options, Wi-Fi MJPEG camera use, and gateway fit for the projection/calibration prototype.
**Status:** Filed

## Executive Recommendation

Spike the ESP32-CAM only as a fixed network camera source. Do not spend prototype time trying to make a classic ESP32-CAM enumerate as a Mac USB webcam, and do not treat it as a candidate gateway computer.

If the board is the common Ai-Thinker-style ESP32-CAM with OV2640, it uses the original ESP32 family and lacks native USB device support. Its micro-USB carrier, when present, is a serial/power adapter, not a UVC camera interface. The realistic path is to flash a camera web-server firmware and have the laptop gateway ingest a JPEG snapshot or MJPEG stream over Wi-Fi.

If the board is actually ESP32-S2/S3-based, USB UVC is possible in principle, but it should be treated as a separate firmware spike. Even then, USB full-speed bandwidth and MJPEG constraints make it a low-end calibration camera, not the final proof of gateway hardware.

## Evidence

- Ai-Thinker ESP32-CAM documentation describes the board as an ESP32-S SoC with an OV2640 1600 x 1200 camera, 520 KB internal SRAM plus 8 MB PSRAM, Wi-Fi, Bluetooth, and interfaces such as UART/SPI/I2C/PWM/ADC/DAC. It lists picture Wi-Fi upload and image formats including JPEG for OV2640, but not native USB video. See the DigiKey-hosted Ai-Thinker datasheet: <https://www.digikey.com/en/htmldatasheets/production/9125147/0/0/1/esp32-cam>.
- Espressif's USB FAQ is explicit: classic ESP32 does not support USB; ESP32-S2/S3 support USB 2.0 full-speed; ESP32-P4 supports high-speed and full-speed. See <https://docs.espressif.com/projects/esp-faq/en/latest/software-framework/peripherals/usb.html>.
- Espressif's `esp32-camera` driver supports ESP32, ESP32-S2, and ESP32-S3 camera sensors including OV2640. It includes JPEG HTTP capture and MJPEG stream examples, which match the network-camera path for a classic ESP32-CAM. See <https://github.com/espressif/esp32-camera>.
- The same camera driver warns that RGB/YUV capture strains the chip, especially when Wi-Fi is enabled, and recommends JPEG capture plus downstream conversion when RGB is needed. That argues for gateway-side CV on the laptop or future Pi, not on the ESP32-CAM.
- Espressif's USB UVC material says ESP32-S2/S3 can transmit camera images to a PC host as a USB camera, and the `usb_device_uvc` component has an ESP32-Sx USB webcam MJPEG example. See <https://docs.espressif.com/projects/esp-techpedia/en/latest/esp-friends/solution-introduction/camera/usb-camera-solution.html> and <https://components.espressif.com/components/espressif/usb_device_uvc/versions/1.3.1/examples?language=en>.
- Espressif's USB UVC notes also show the practical ceiling: USB full-speed/MJPEG constraints are in the low-resolution camera range, with example figures around 800 x 480 at 15 fps in bulk mode or 480 x 320 at 15 fps in synchronous mode. This is acceptable for a cheap calibration-source spike, not a reason to choose the final camera yet.
- ESP-WHO shows that Espressif SoCs can run some embedded vision workloads, especially on ESP32-S3/P4, but those are FreeRTOS/firmware pipelines for constrained tasks like face or QR detection. They are not a replacement for the repo's current gateway responsibilities: serving the web UI, ingesting maps, running OpenCV-style calibration, driving an HDMI projector output, and keeping manual controls responsive. See <https://developer.espressif.com/blog/2026/05/esp-who-get-started/>.

## Product Fit

- Ideal refs: Physical Table First, Speed Over Polish, Calibration Is Product Core, Robust Manual Control
- Spec refs: `spec:2.1`, `spec:2.2`, `spec:3.1`, `spec:6.1`
- Story refs: `story-001-calibration-projection-spike`
- ADR refs: ADR-001 keeps camera profile, fixed rig profile, and per-session acquisition separate. This scout does not require a new ADR unless the project chooses a durable gateway/camera hardware family.

## Candidate Uses

| Use | Fit | Recommendation |
|---|---|---|
| Classic ESP32-CAM as USB webcam | Poor | Reject. Classic ESP32 has no USB device support, and USB carrier boards are serial adapters. |
| Classic ESP32-CAM as Wi-Fi MJPEG/snapshot camera | Good enough for a spike | Spike. Mount it rigidly to the projector, stream JPEG/MJPEG over local Wi-Fi, and ingest it in the laptop gateway. |
| ESP32-S2/S3 camera board as USB UVC webcam | Possible but narrow | Defer or spike only if the available board is actually S2/S3 and wiring exposes native USB. Expect low-res MJPEG. |
| ESP32-CAM as final representative camera | Weak | Defer. Its lens, sensor, compression, Wi-Fi path, rolling exposure, and low-light behavior may differ from the eventual fixed webcam. Useful as a worse-case cheap source. |
| ESP32-CAM as gateway/minicomputer | Poor | Reject for MVP gateway role. It cannot drive the HDMI projector path and is too constrained for the web UI plus CV pipeline. |
| ESP32-S3/P4 class board as future embedded CV companion | Plausible later | Defer. Consider only after Pi-class gateway sizing evidence exists. |

## Recommended Spike Shape

1. Confirm the exact board marking: classic ESP32-CAM versus ESP32-S3/S2 camera board.
2. If classic ESP32-CAM, flash a known camera web-server firmware using `esp32-camera`.
3. Lock it to the local network and expose a stable `/capture` JPEG endpoint and/or MJPEG stream URL.
4. Add or manually test a gateway-side network-camera ingest path, preferably same-origin through the laptop gateway so browser canvas/CORS rules do not block CV access.
5. Mount the board to the projector as rigidly as possible and capture the same blank-mat and alignment-pattern frames currently captured from the phone.
6. Record stream resolution, latency from capture click to usable still, focus/field-of-view, exposure/glare behavior, and whether manual seed remains usable.
7. Keep the laptop as the gateway and projector driver for this spike.

## Adoption Decision

- Decision: Spike
- Why: It may remove the phone from the calibration loop quickly, and a fixed cheap camera is closer to the intended rig than Continuity Camera ergonomically. It should not change the gateway architecture or final hardware assumptions yet.
- Follow-up owner: Story 001 physical calibration pass or a small follow-up hardware-source story. Create a new ADR only when choosing durable camera/gateway hardware.

## Risks And Open Questions

- The board variant matters. "ESP32-CAM" usually means classic ESP32, but some newer boards use ESP32-S3 and have different USB options.
- Wi-Fi MJPEG is not visible to browser `getUserMedia` as a normal camera. The app needs an IP-camera ingest/proxy path or a virtual-camera bridge.
- Browser CV against a cross-origin camera stream can be blocked unless the ESP firmware provides permissive CORS headers or the gateway proxies the image.
- USB UVC on ESP32-S2/S3 is full-speed and MJPEG-constrained, so it may not outperform a cheap USB webcam.
- ESP32-CAM optics and exposure may be poor in dim projector/table lighting. That is useful stress evidence, but it should not be mistaken for final camera quality.
- The ESP32-CAM has no HDMI/projector output path and should not displace the laptop/Pi-class gateway role.
