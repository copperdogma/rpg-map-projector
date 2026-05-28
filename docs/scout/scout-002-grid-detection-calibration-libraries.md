# Scout 002 - Grid Detection And Calibration Libraries

**Source / Question:** Are there open-source models or libraries that can solve battle-mat grid detection, or should RPG Map Projector keep rolling its own detector?
**Scouted:** 2026-05-28
**Scope:** Open-source calibration targets, fiducial markers, homography/calibration APIs, line-segment detectors, and grid/table models relevant to Story 001 projection calibration.
**Status:** Filed

## Executive Recommendation

Spike an OpenCV-backed active calibration path before further hardening the hand-rolled passive grid detector.

Do not expect an open-source model to identify arbitrary RPG battle-mat grids reliably from sales photos or messy table frames. The stronger open-source path is to use mature calibration and marker tools, then keep custom code only for product-specific glue: choosing the calibration flow, mapping physical mat coordinates to projector pixels, gating bad results, and providing direct manual correction.

The current browser detector should remain useful as a prototype harness and passive helper. It should not become the main product bet unless real hardware evidence proves that passive mat-grid detection is robust enough.

## Evidence

- OpenCV exposes the calibration and geometry tools that match this problem better than the current custom detector: `findChessboardCorners`, `findChessboardCornersSB`, `findCirclesGrid`, `calibrateCamera`, `solvePnP`, and `findHomography`. These are designed around known calibration patterns and point correspondences rather than semantic recognition of arbitrary grids.
- OpenCV's ArUco module supports generated square fiducial markers, marker dictionaries, marker detection, corner extraction, and pose estimation. This is a strong fit for an active or assisted calibration workflow because marker identity and corner ordering are explicit instead of inferred from repeated mat lines.
- AprilTag is an open-source fiducial system used in robotics. The upstream AprilTag 3 repository provides a small C library, Python wrapper path, OpenCV integration notes, tag families, and pose-estimation support. This is another strong candidate for printed calibration markers or a temporary calibration target.
- OpenCV's Hough and line-segment functionality is useful but lower-level. It finds lines or line segments; it does not know which lines are the playable battle-mat grid, where the intended projection span begins, or which sales-photo inset/packaging lines are irrelevant.
- DeepLSD and M-LSD are open-source learned line-segment detectors. They may improve line extraction under weak lighting or perspective distortion, but they still output generic line segments. They do not solve grid ownership, outer-corner selection, source scale, physical-mat coordinate selection, or projector feedback.
- Table Transformer and similar table-structure models are not a product fit. They are trained for document/PDF table extraction and table-cell structure, not camera/projector calibration against a wet-erase mat in a physical play scene.

## Adoption Decision

- Decision: Spike
- Why: Mature CV libraries can probably replace the fragile parts of the custom detector, but the exact runtime boundary is still open: OpenCV.js in the gateway-hosted web UI, Python/OpenCV on the gateway, native OpenCV on a future Raspberry Pi image, AprilTag C bindings, or some hybrid.
- Follow-up owner: Story 001 or a follow-up calibration story. Create an ADR only if the spike chooses a durable runtime dependency or gateway/server boundary for OpenCV, AprilTag, or native CV processing.

## Recommended Spike Shape

Test three calibration modes against the existing `input/map-pix/` fixtures and then against real camera frames:

1. Passive OpenCV line/grid path: undistort/normalize, line-segment or Hough detection, cluster two orthogonal line families, solve homography from selected grid intersections.
2. Fiducial-assisted path: place temporary printed ArUco/AprilTag markers or a calibration card at known mat coordinates, detect marker corners, solve mat-to-camera pose/homography.
3. Active projector-camera path: project known bright calibration points or coded markers, capture them with the fixed camera, solve projector-to-camera mapping, then combine with mat-grid or marker coordinates.

Success should be measured by physical error, setup time, and failure mode clarity, not by a confidence score alone.

## Product Fit

- Ideal refs: Calibration Is Product Core, Speed Over Polish, Physical Table First, Robust Manual Control
- Spec refs: `spec:2`, `spec:3.1`, `spec:5.1`, `spec:6.1`, `spec:7.1`
- Story refs: `story-001-calibration-projection-spike`
- ADR refs: None yet. Create one if adopting a non-browser CV runtime or fiducial-based calibration architecture as a durable dependency.

## Risks And Open Questions

- OpenCV.js may not expose every needed contrib/fiducial feature cleanly in the browser; gateway-side Python/OpenCV may be simpler on a laptop/Raspberry Pi.
- Printed markers may be a setup burden unless they can live on a reusable calibration card, mat-edge strip, or projector/camera mount.
- Projected markers can calibrate projector-to-camera mapping, but they do not by themselves identify the physical mat grid unless paired with known physical markers, passive mat-grid detection, or manual point marking.
- Passive line detection may work better on real fixed-camera frames than sales photos because the scene is controlled, but it still needs a labelled error harness before it can be trusted.
- A learned line detector may help if lighting is poor, but adding ML inference before exhausting OpenCV/fiducials would increase runtime complexity without solving the product-specific geometry.
