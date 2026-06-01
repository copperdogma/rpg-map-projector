# ADR-001 Final Synthesis - Layered Calibration Architecture

## Recommendation

Adopt the layered calibration architecture:

1. camera profile for intrinsics and lens distortion,
2. fixed projector-camera rig profile for mounted hardware geometry,
3. per-session scene acquisition for the current mat/grid,
4. residual checks and manual fallback before accepting a live projection.

## Why

This matches the physical system. Some facts are stable only while the camera, projector, mount, resolution, focus, and capture settings remain fixed. Other facts change every session, especially the mat position, table height, lighting, curl, glare, occlusion, and current playable grid extent.

The existing scouts and synthetic active-calibration harness support projection-mapping style active evidence for projector-camera calibration, while the real-photo grid work shows why passive arbitrary-grid detection should remain a helper instead of the only product bet.

## Risks And Tradeoffs

- Profile invalidation becomes part of the product: a cached calibration must be rejected or refreshed when hardware settings or mount geometry change.
- The product still needs startup scene acquisition; fixed rig calibration does not remove the need to find the current mat/grid.
- Physical proof may show that a single homography is insufficient, requiring a later mesh-warp or structured-light ADR.
- The final CV runtime boundary remains open until hardware evidence shows whether browser/OpenCV.js, gateway-side Python/OpenCV, native OpenCV, or fiducial bindings are the right dependency path.

## Follow-Up

- In the physical hardware pass, compare one-frame projected coded fiducials against two-frame fiducial-plus-circle refinement.
- Add camera intrinsics/undistortion before treating curved residuals as detector or projection failure.
- Measure physical projected-grid error on the mat and record setup time.
- Create a separate ADR before adopting a durable OpenCV/AprilTag runtime boundary, dense structured-light setup flow, or mesh-warp projection model.
