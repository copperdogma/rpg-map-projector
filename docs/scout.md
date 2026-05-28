# Scout Index

Scouting records external sources, hardware options, libraries, implementation patterns, and product references that may affect RPG Map Projector.

Use scout work when the next move depends on external evidence rather than repo-local implementation. Keep the result decision-shaped: adopt, adapt, defer, reject, or spike.

| # | Source | Date | Scope | Recommendation | Follow-Up | Status |
|---|---|---|---|---|---|---|
| 001 | [Existing Battle Map Projection Solutions](scout/scout-001-existing-battle-map-projection-solutions.md) | 2026-05-27 | Existing in-person map projection, fog, QR/player views, true-scale rendering, and camera/projector calibration references | Spike Mappadux before building projection/pairing from scratch; do not adopt wholesale yet | Story 001 includes the Mappadux spike; create ADR only if choosing fork/adopt/base architecture | Filed |
| 002 | [Grid Detection And Calibration Libraries](scout/scout-002-grid-detection-calibration-libraries.md) | 2026-05-28 | Open-source calibration targets, fiducial markers, homography/calibration APIs, line-segment detectors, and grid/table models relevant to Story 001 | Spike an OpenCV-backed active calibration path; keep passive custom grid detection as helper, not the main product bet | Story 001 or follow-up calibration story; create ADR only if adopting a durable OpenCV/AprilTag runtime boundary | Filed |
