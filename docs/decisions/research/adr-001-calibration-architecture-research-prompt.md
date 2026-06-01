# ADR-001 Research Prompt - Layered Calibration Architecture

Created: 2026-05-30

## Context

RPG Map Projector needs to project source maps onto a real 1-inch battle mat fast enough for live tabletop play. The likely home setup is a fixed webcam mounted to an HDMI projector, both connected to a local gateway. The laptop is the current stand-in for the future gateway.

Existing project evidence suggests calibration should not be treated as one monolithic runtime solve:

- passive grid detection is useful but fragile under arbitrary photos, props, crop, glare, mat curl, and lens distortion,
- OpenCV-style calibration targets, fiducials, homography, and undistortion primitives are a strong fit for known geometry,
- projection-mapping techniques suggest active projected evidence for projector-camera calibration,
- synthetic active-calibration evidence currently favors comparing one-frame coded fiducials against two-frame fiducial-plus-circle refinement before dense structured light.

The proposed architecture separates camera intrinsics/lens distortion, fixed projector-camera rig calibration, and per-session mat/grid acquisition.

## What I Need

1. Is the layered split between camera profile, fixed rig profile, and per-session scene acquisition the right architecture for this product?
2. What real-world failure modes should invalidate cached camera or rig calibration profiles?
3. Which first physical spike should best test this architecture: coded fiducials, circle/dot grids, two-frame refinement, ChArUco, printed marker strips, or another target?
4. What should be measured in physical tests to decide whether homography is enough or mesh/structured-light correction is needed?

## Output Format

For each major option, provide:

1. Recommended choice with reasoning
2. Main tradeoffs and failure modes
3. What would need to be true for a different choice to win
4. Evidence or examples
