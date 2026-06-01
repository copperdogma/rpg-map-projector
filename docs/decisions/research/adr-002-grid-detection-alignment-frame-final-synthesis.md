# ADR-002 Final Synthesis - Grid Detection Alignment Frame

## Recommendation

Accept the grid-as-alignment-frame approach for the current calibration discovery path.

Use grid detection to establish the physical grid coordinate system. Do not require the detector to prove the exact physical mat boundary before the DM can project a map.

## Why

The evidence split cleanly:

- lattice alignment is now strong enough to be useful on the current real-home image corpus,
- boundary ownership remains subjective and fragile under shadows, occlusions, crop, curl, and glare,
- the DM workflow primarily needs projected map content to line up with the physical grid, not a visible debug grid that exactly ends at the mat edge,
- conservative supported extents were too small for practical map placement,
- bounded frame extents preserve alignment and useful coverage without pretending to segment the mat.

This fits the product values: fast table utility, robust manual control, and physical-table-first behavior.

## Risks And Tradeoffs

- The internal grid can extend past the real mat. That is acceptable if the grid is normally invisible and the DM controls map placement, but it may need warnings later.
- The decision does not prove runtime readiness. The current AI-assisted evidence still needs a larger real-camera corpus and physical projection validation.
- Physical mat-boundary detection may still be useful later for clipping, warnings, or automatic fit-to-mat controls.
- Optional AI evidence should not become an MVP live dependency unless local-only detection fails and the product explicitly accepts cloud latency and availability tradeoffs.

## Follow-Up

- Update Story 003 closeout to separate sales-photo OpenCV success, real-home AI grid alignment success, and deferred mat-boundary ownership.
- Keep `npm run benchmark:ai-grid-frame-summary` as the report for this decision.
- Move the next proof to real-camera and physical projection evidence rather than more boundary-mask tuning.
- If map-placement UX later needs it, create a separate story for optional physical-mask/warning behavior.
