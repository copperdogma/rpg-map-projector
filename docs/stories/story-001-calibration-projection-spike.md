---
{
  "title": "Calibration Projection Spike",
  "status": "Pending",
  "priority": "High",
  "origin": "Kickoff identified physical calibration and projection alignment as the largest real risk before app, remote server, or AI cleanup work.",
  "ideal_refs": ["docs/ideal.md"],
  "spec_refs": ["spec:2", "spec:3.1", "spec:6", "spec:7.1"],
  "depends_on": [],
  "category_refs": ["spec:2", "spec:3", "spec:6", "spec:7"],
  "compromise_refs": ["B2", "B3", "B7"]
}
---

# Story 001: Calibration Projection Spike

## Goal

Prove that a rough laptop-as-gateway + HDMI projector + fixed camera rig can project a source grid onto a real 1-inch battle mat accurately and quickly enough to be useful at the table.

## Background

The first hardware path does not assume a dedicated USB webcam. An iPhone can act as a remote camera fixed to the projector with a temporary cardboard or printed mount. The likely finished home rig uses a cheap webcam fixed to the projector and plugged into a Raspberry Pi or similar mini-computer. This keeps the camera/projector relationship repeatable while still requiring per-placement calibration against the physical mat.

This story intentionally does not require remote storage/auth, native iOS, AI cleanup, map libraries, or app polish.

## Scope

Build the smallest experiment that can:

- show a calibration pattern through the projector,
- capture the battle mat and projected pattern through the fixed camera feed,
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
- The test records camera/projector placement notes and any failure modes.
- The result is good enough to decide whether the next story should improve calibration, projection display, source-map normalization, UI controls, or hardware selection.

## Non-Goals

- Full phone controller UI.
- Polished map import.
- Remote storage/auth.
- Native iOS app.
- AI Auto-Clean.
- Inpainting or Clean/Hide Pen.
- Saved map library.
- Automatic perfect grid detection.

## Work Log

- 20260527-0000 — Created during greenfield setup as the first physical proof story.
