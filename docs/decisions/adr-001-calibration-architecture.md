# ADR-001 - Layered Calibration Architecture

## Status

Accepted

## Context

The product only works if the projected map lands on the physical battle mat quickly enough for live table play. Early passive grid-detection work showed that mat-grid evidence, camera lens distortion, mat curl, projector-camera geometry, and current table placement can be easy to conflate if the system treats calibration as one monolithic runtime solve.

The likely home setup is a fixed webcam mounted to an HDMI projector, both connected to a local gateway. That makes some calibration reusable across sessions, but not all of it. The camera may need a reusable lens/intrinsic profile. The mounted projector-camera pair may need a reusable rig profile. Each play session still needs to locate the current table/mat/grid because the mat placement, table height, curl, lighting, and occlusions can change.

This is a durable architecture choice because it shapes hardware setup, UI flow, CV runtime boundaries, evaluation criteria, and future stories. It should be recorded before later work accidentally optimizes only one layer.

## Decision

Use a layered calibration architecture:

1. **Camera profile:** calibrate camera intrinsics and lens distortion for a specific camera, resolution, focus, and capture mode. Use this profile to undistort calibration frames before interpreting curved line residuals as algorithm failures.
2. **Fixed rig profile:** with the camera mounted to the projector, calibrate projector pixels to camera coordinates using active projected evidence such as coded fiducials, projected circles/dots, or a two-frame fiducial-plus-circle refinement. Cache this profile only while the mount, projector settings, camera settings, focus, zoom, and resolution remain stable.
3. **Per-session scene acquisition:** on each startup, capture the current table scene, apply the camera profile, detect or confirm the physical mat/grid in current camera coordinates, combine that with the fixed rig profile, and compute the projector transform for the current mat placement.
4. **Verification and fallback:** use residual gates, optional projected check patterns, and fast manual correction before accepting a solve. Passive grid detection remains useful as a helper and fallback, but the durable product path should not depend on passive arbitrary-grid detection alone.

This ADR does not choose the final marker family, exact OpenCV runtime boundary, hardware model, or whether a later mesh warp is needed. Those remain evidence-driven follow-up decisions.

## Options Considered

- Single runtime passive mat-grid solve: simplest user flow and no setup target required, but current evidence shows arbitrary grid ownership is fragile under photos, props, cropping, glare, curl, and lens distortion. Rejected as the primary architecture; retained as a helper/fallback.
- One fixed projector-camera calibration with no session acquisition: attractive once the camera is mounted to the projector, but it cannot know where the mat sits today or whether the table height, mat placement, or projector angle changed. Rejected as incomplete.
- Layered camera, rig, and session calibration: separates stable camera/rig facts from volatile table-scene facts. Accepted because it matches the physical setup and keeps each solve accountable to the right source of error.
- Dense structured-light or mesh-first calibration: powerful for projector-camera systems, but likely too pattern-heavy for first live-play workflow. Deferred until physical evidence shows sparse homography plus residual checks cannot meet accuracy.

## Consequences

Positive:

- Clarifies why the system still needs startup scene/grid acquisition even after the camera and projector are mounted together.
- Gives future stories a clean split between camera calibration, projector-camera calibration, and live mat/grid detection.
- Makes lens undistortion a setup/profile concern instead of forcing every passive grid detector to absorb camera distortion implicitly.
- Supports a local-first live loop: calibration and projection can run on the gateway without requiring a remote server.
- Keeps manual correction and refusal states honest when one layer is stale or low-confidence.

Tradeoffs:

- Requires storing and invalidating calibration profiles keyed to camera/projector settings and mount stability.
- Adds a setup or maintenance flow before the product reaches plug-and-play behavior.
- Does not eliminate hard scene understanding; the current mat/grid must still be located per session.
- May require later ADRs if the implementation adopts native OpenCV, AprilTag/ArUco, dense structured light, or mesh warping as durable dependencies.

## References

- Ideal: `docs/ideal.md` - Calibration Is Product Core, Speed Over Polish, Physical Table First, Robust Manual Control
- Spec: `docs/spec.md` - `spec:6.1` Calibration
- State/Graph: `docs/methodology/state.yaml` marks `spec:6` partial and real-camera/physical-projection goldens deferred until hardware measurements; `docs/methodology/graph.json` registers `eval:active-fiducial-sim`
- Scouts: `docs/scout/scout-002-grid-detection-calibration-libraries.md`, `docs/scout/scout-003-projection-mapping-calibration-techniques.md`
- Stories: `docs/stories/story-001-calibration-projection-spike.md`, `docs/stories/story-003-calibration-algorithm-discovery-evaluation.md`
- Related decisions: None found before ADR-001

## Open Questions

- What physical error threshold is acceptable at the table: center-line error, square-edge error, or maximum local warp error?
- Which active pattern wins on real hardware: coded fiducials, anonymous/asymmetric circles, two-frame refinement, or another projected target?
- Does a single homography remain sufficient after camera undistortion, or do projector lens distortion, mat curl, or off-axis projection require a small mesh correction?
- What profile invalidation checks are enough to detect a bumped mount, changed focus, changed camera resolution, changed projector mode, or stale exposure?
