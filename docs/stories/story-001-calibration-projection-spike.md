# Story 001: Calibration Projection Spike

Status: Planned

## Goal

Prove that a rough laptop + HDMI projector + iPhone camera rig can project a source grid onto a real 1-inch battle mat accurately and quickly enough to be useful at the table.

## Background

The first hardware path does not assume a dedicated USB webcam. Instead, an iPhone can act as a remote camera fixed to the projector with a temporary cardboard or printed mount. This keeps the camera/projector relationship repeatable while still requiring per-placement calibration against the physical mat.

## Scope

Build the smallest experiment that can:

- show a calibration pattern through the projector,
- capture the battle mat and projected pattern through the iPhone camera feed,
- manually or semi-automatically identify the mat grid,
- compute a planar transform from desired mat coordinates to projector pixels,
- project a test grid aligned to the physical mat,
- support manual nudge, scale, and rotation correction.

## Acceptance Criteria

- A real or printed 1-inch grid can be used as the calibration target.
- A source grid can be projected so 5 ft squares align 1:1 with physical squares.
- A 10 ft source-grid mode can project each source square as 2 by 2 physical squares.
- The projected grid can be nudged, scaled, and rotated without restarting the whole flow.
- The test records approximate alignment error in inches or fractions of a mat square.
- The test records setup time from starting calibration to useful projection.
- The result is good enough to decide whether the next story should improve calibration, projection display, source-map normalization, or UI controls.

## Non-Goals

- Full phone controller UI.
- Polished map import.
- AI Auto-Clean.
- Inpainting or Clean/Hide Pen.
- Saved map library.
- Automatic perfect grid detection.

## Notes

The story should prefer empirical proof over architecture. A simple OpenCV script, local web page, or small prototype app is enough if it produces a real projected alignment result.
