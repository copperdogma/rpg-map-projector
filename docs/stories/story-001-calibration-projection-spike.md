---
{
  "title": "Calibration Projection Spike",
  "status": "In Progress",
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

Scout 001 identified Mappadux / Dynamic Map Renderer v2 as close prior art for QR pairing, local web projection, fog, and true-table-scale rendering. Before building the projection UI from scratch, this story should run a short Mappadux spike to decide whether to fork/adapt the codebase, borrow specific projection/scaling concepts, or proceed independently.

## Scope

Build the smallest experiment that can:

- inspect Mappadux's projector, pairing, and scaled-view architecture against this story's camera-calibrated projection needs,
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
- The test records whether Mappadux should be forked/adapted, used as implementation reference only, or rejected for this product.
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

## Implementation Plan

- [x] Use Scout 001 to decide whether Story 001 should fork/adapt Mappadux or borrow concepts only.
- [x] Create the smallest local web calibration workbench: controller view, projector view, calibration grid, source scale toggle, and manual nudge/scale/rotate controls.
- [x] Add local false-input image support and a first-pass software grid detector before requiring a physical mat.
- [x] Simulate the detect-to-project loop with browser screenshots before physical hardware is available.
- [x] Add a fixture-labeling workbench so local false inputs can become scored detector benchmarks.
- [x] Add homography math tests so the transform behavior is not only visually inspected.
- [x] Add browser smoke coverage for the controller/projector surfaces.
- [x] Record current evidence, hardware gaps, and next physical-test instructions in this story.
- [ ] Run a physical projector/camera session and record real alignment error, setup time, placement notes, and failure modes.

## Current Mappadux Decision

Use Mappadux as implementation reference only for Story 001. Borrow concepts around a separate projector view, true-table-scale thinking, static/PWA viability, local storage, and future QR/pairing. Do not fork or adapt it yet because its architecture is optimized for a broad VTT-at-home workflow and does not solve this story's fixed camera/projector homography against a real mat.

## Current Evidence

- Added a Vite/TypeScript calibration workbench with a controller view at `/` and projector view at `/projector.html`.
- The controller can start a browser camera feed when one is available, falls back to a synthetic mat preview, and syncs calibration state to the projector view through local storage plus `BroadcastChannel`.
- The projector view renders a calibration quadrilateral and grid from four physical-mat-to-projector anchor pairs.
- Added an Auto Grid Detection panel that can analyze a generated test mat, uploaded image, or local false camera input from `input/map-pix/`.
- Local false inputs are intentionally ignored by git because they may be third-party sales images; the committed app only references them as optional dev fixtures.
- Added a fixture-labeling workbench at `/labeler.html`. It lets a reviewer pick each false input, drag four grid corners, use a large hold-to-zoom reticle for precise placement, toggle the virtual grid overlay for before/after visual checks by checkbox or `G`, adjust row/column counts by buttons or shortcuts (`C` / `Shift+C`, `R` / `Shift+R`), mark whether it should be used for benchmark scoring, and save labels to `input/map-grid-labels.json` through the local Vite dev server. Saved fixtures immediately refresh from `unlabeled | unsaved changes` to `labeled` and reload as the default label when returning to that fixture. Fixture labels now support extrapolated grid corners outside the source bitmap, so sales photos or camera frames that crop off the mat edge can still capture the true full grid instead of forcing the label inside the visible photo.
- The current saved label file contains all 12 available false inputs: the generated test mat plus 11 local mat photos. The labels are committed as `input/map-grid-labels.json`; the third-party source photos remain ignored under `input/map-pix/`.
- The first-pass detector uses image edges, roughly orthogonal line families, regular line spacing, and lattice-support checks to estimate battle-mat corners, row/column counts, and confidence.
- Detected corners render as draggable orange handles on the preview, making direct visual correction the primary fallback when auto detection is close but wrong.
- Auto detection now applies detected corner bounds to the projector anchors only when quality gates pass. The real camera-to-projector delta still needs separate calibration when hardware is attached.
- The preview overlay now shows the current physical projection span fitted to the detected corners, rather than trusting the detector's rough row/column count.
- Added a stricter axis-aligned grid pass for clean straight-on inputs. The generated test mat now detects as 12 x 8 with known corner error under 5 px; the previous 8 x 4 partial detection is no longer accepted by tests.
- Added a bright-on-dark projected-grid detector so a projector screenshot can still be fed back as a simulated camera frame and auto-aligned.
- Added lattice-support scoring so a plausible-looking quadrilateral is not enough to auto-align; proposed grid lines must line up with repeated line evidence in the image.
- Rejected detections now render as orange dashed candidates with `Candidate only; not applied` status, warning styling, lattice-support percentage, `Force Apply Candidate` labeling, and unchanged projector anchors. The green projected grid is reserved for accepted auto-align passes.
- Axis-aligned sales-photo candidates now use thin-line contrast and occlusion-tolerant lattice runs before the generic Hough fallback. This improved the representative `Local mat photo 7` case from a visibly cropped skew to a rough top-mat candidate while still refusing auto-apply because it is a 28 x 26 full-mat grid, not the current 12 x 8 calibration span.
- Generic Hough detections with out-of-frame corners are now rejected outright. In the current false-input set this changes `Local mat photo 10` from an unsafe packaging-bound candidate into a clean `No reliable grid found` state.
- Added a Conductor allocation-backed local runtime launcher. The primary checkout now uses `http://127.0.0.1:5178/` for the controller and `http://127.0.0.1:5178/projector.html` for the projector view; worktrees derive stable ports from the `rpg-map-projector` allocation.
- Quick external algorithm check: OpenCV's Hough guidance matches the current edge/line-family approach, but OpenCV also exposes Line Segment Detector, chessboard/circle-grid calibration, and homography APIs. If real-camera detection stays weak, create a scout for OpenCV.js / WASM line-segment or fiducial calibration instead of further hardening the hand-rolled browser detector.
- Manual fallback controls still exist for source scale (`5 ft` or `10 ft` source squares), nudge, scale, rotate, anchor coordinate edits, brightness, and visibility toggles.
- Session evidence fields capture setup time, measured error, placement notes, failure modes, and exportable JSON.
- Unit tests cover homography solving, manual transform helpers, detected-grid-to-projector anchor mapping, and known-corner accuracy for a synthetic grid. Browser tests cover controller rendering, projector rendering, fixture-labeler rendering/edit controls, save-state refresh, saved-label reload, virtual-grid checkbox and shortcut toggling, row/column shortcuts, drag reticle visibility, extrapolated off-image fixture corners, source-scale persistence, generated false-input detection with 12 x 8 / under-5-px corner accuracy, rejected-candidate UI copy/styling, and a projector screenshot fed back as a simulated camera frame.
- Local false-input scan on 2026-05-27 after the stricter lattice gate: the generated test mat and projected-grid screenshot auto-align; all 11 third-party sales photos are candidate-only / not applied because their proposed grids have low lattice support, out-of-frame corners, or too little usable grid area. These sales photos are useful negative fixtures, not proof that real camera calibration is solved.
- Simulated screenshot evidence was captured under `test-results/story-001-lattice-gated-sample-0.png`, `test-results/story-001-lattice-gated-sample-7.png`, `test-results/story-001-lattice-gated-sample-8.png`, and `test-results/story-001-lattice-gated-sample-10.png`. A delegated visual review accepted the generated control image as credible auto-align evidence, accepted `Local mat photo 7` only as a warning-state candidate, flagged `Local mat photo 8` as an inset partial candidate, and flagged the previous `Local mat photo 10` packaging-bound rectangle as visually invalid. The follow-up code now rejects `Local mat photo 10` cleanly while keeping `Local mat photo 8` warning-only because it is below confidence and larger than the current 12 x 8 calibration span.

## Remaining Physical Evidence

This story is not complete until hardware is attached. The next pass needs an HDMI projector or second display plus a camera source, then should record:

- approximate alignment error in inches or fractions of a mat square,
- setup time from opening the workbench to useful projection,
- whether direct visual tuning or camera-feed tuning is faster,
- camera/projector placement notes,
- whether detected camera-space grid corners can drive the projector-space transform quickly enough,
- whether the simulated camera-image-to-projector fit should become a real camera-to-projector calibration model or be replaced by a hardware-specific calibration routine,
- whether direct corner dragging is sufficient when auto detection is wrong,
- whether the manual nudge/scale/rotate controls are still needed beyond debug recovery,
- whether the next story should improve calibration, source-map normalization, UI controls, or hardware selection.

## Work Log

- 20260527-0000 — Created during greenfield setup as the first physical proof story.
- 20260527-0001 — Added Scout 001 Mappadux spike as the first implementation check.
- 20260527-0002 — Started Story 001; chose a narrow local calibration workbench over forking Mappadux.
- 20260527-0003 — Added the local controller/projector calibration workbench, homography tests, Playwright smoke tests, and current evidence notes.
- 20260527-0004 — Added local battle-mat photo fixtures as ignored false camera inputs, first-pass grid detection, draggable detected-corner correction, and sample-scan evidence.
- 20260527-0005 — Added simulated detect-to-project alignment: detected corners now update projector anchors, manual corner dragging re-applies anchors, and Playwright feeds a projector screenshot back as a fake camera frame.
- 20260527-0006 — Raised validation standards after visual review exposed a partial false positive on the generated mat; added known-corner gates and an axis-aligned detector path for clean inputs.
- 20260527-0007 — Reworked Hough selection toward regularly spaced line families, added lattice-support scoring, rejected bad sales-photo detections as candidate-only, added a bright-on-dark projected-pattern detector, and updated the UI so rejected candidates are not visually presented as applied projection alignment.
- 20260528-0715 — Added Conductor port allocation and local launcher/status/stop commands for the Story 001 workbench; verified controller and projector views on assigned UI port 5178 with `npm run check`.
- 20260528-0800 — Tightened false-input detection after visual review: added thin-line axis scoring, occlusion-tolerant axis lattice runs, a minimum axis lattice floor, a 12 x 8 auto-align span gate, and Hough in-frame rejection so bad sales-photo detections stay warning-only or fail cleanly.
- 20260528-0915 — Added the grid fixture labeler so local false inputs can be saved as benchmark ground truth before the next detector iteration loop.
- 20260528-0935 — Added a hold-to-zoom reticle to the fixture labeler corner-drag interaction for precise grid-corner placement.
- 20260528-0950 — Enlarged the fixture-labeler drag magnifier and added a virtual-grid overlay toggle for visual alignment checks.
- 20260528-1005 — Fixed fixture-labeler save feedback so saved labels immediately show as labeled and reload by default when returning to a fixture.
- 20260528-1015 — Added a `G` shortcut for toggling the fixture-labeler virtual grid overlay without triggering while row/column inputs have focus.
- 20260528-1025 — Added visible shortcut hints and keyboard shortcuts for row/column fixture-label adjustments.
- 20260528-1045 — Added extrapolated fixture-grid labeling so benchmark corners can sit outside the visible bitmap, with a padded label workspace and drag-stable off-image corner coverage.
- 20260528-1705 — Saved labels for all 12 current false inputs and kept the source image folder ignored.
