# ADR-002 - Grid Detection Alignment Frame

## Status

Accepted

## Context

Story 003 started as a calibration algorithm discovery story with a strict sales-photo benchmark: find the physical battle-mat extent, exact row/column counts, and corner positions. Gateway-side OpenCV eventually reached 11/11 on those sales photos, but the result used narrow product-photo-family branches and configured mat dimensions. That made it useful benchmark evidence, not enough proof of real table behavior.

The later real-home image lane changed the practical problem. Optional AI evidence, especially Grok-generated grid masks plus local geometry parsing, could align very closely to the visible physical grid. The hard part was no longer "can we find a grid family?" It was "where should the grid stop?" Real photos include missing mat edges, off-image corners, shadows, glare, head occlusion, green foreground material, curled mat areas, and subjective human labels about when the grid should be considered over.

The product does not actually need the automatic detector to know the exact physical mat boundary before the DM can use the system. The live projection path needs a coordinate frame aligned to the physical grid so the DM's map can snap, scale, nudge, and project correctly. The DM should not need to see or care that the internal grid extends beyond the visible mat unless they intentionally place projected content there.

This is a durable product and architecture decision because it changes eval interpretation, labeler defaults, runtime promotion criteria, and future calibration stories. It also prevents the project from spending more time optimizing a brittle "mat ownership" classifier that may not matter for MVP usability.

## Decision

Treat detected physical grid evidence as an internal alignment coordinate frame, not as an authoritative physical mat boundary.

For the current proof path:

- preserve the best no-label selected homography from the AI/grid evidence pipeline,
- expand the aligned grid across the source image as a bounded frame,
- cap each axis at 100 cells to prevent extreme perspective blowups,
- trim edge rows or columns whose sampled band has less than 10% source-photo overlap,
- keep the full extrapolated coordinate frame available in the labeler/debug overlay,
- render the source-photo-overlapping portion more prominently for inspection,
- do not project a visible grid by default in the DM workflow.

The live product should project the map image onto the aligned coordinate frame. The grid overlay is a debug, calibration, or manual-correction aid, not the primary player-facing output.

Do not promote material-aware dark/light or "is this still mat?" masking as part of this Story 003 decision. It was tested and rejected for now because a deliberate head-shadow case caused a valid grid region to be dimmed as non-material. Physical mat-boundary detection can become a later additive feature if projection/map-placement UX proves that users need it.

ADR-001 still stands: passive grid detection is one layer in a larger calibration architecture. This ADR only chooses how to interpret a detected grid during the current passive/AI-assisted discovery path.

## Options Considered

- Exact physical mat boundary detection: Plausible because it would make the automatic result match human labels and avoid over-projecting beyond the mat. Rejected for Story 003 because the boundary is subjective under cropped photos, curl, glare, shadows, props, and occlusions, and because the product can work without proving it.
- Conservative supported patch only: Plausible because it avoids extrapolating beyond strong observed evidence. Rejected as the default because it aligned well but produced grids that were too small for useful projection. On the current real-home corpus, old supported extents covered only 27.393% mean and 10.727% minimum of visible labeled intersections.
- Bounded image-frame alignment coordinate frame: Accepted. It keeps the high-quality lattice alignment, expands to a usable internal coordinate frame, caps pathological perspective, and trims rows/columns that barely touch the source photo. On the current real-home corpus, it covers 99.95% mean and 99.598% minimum of visible labeled intersections.
- Material-aware bright/dim overlay: Rejected for now. It can remove some obvious non-mat regions, but shadows can make real grid regions look non-material, creating false negatives in exactly the kind of table conditions the product must survive.
- Active/fiducial calibration only: Deferred as an exclusive replacement. It remains important in the layered calibration architecture, but it does not invalidate the current passive grid-frame result as a useful scene acquisition and manual-correction input.

## Consequences

Positive:

- Separates lattice alignment from physical mat-boundary ownership.
- Turns a difficult visible-boundary problem into a simpler and more useful coordinate-frame problem.
- Reduces overfitting pressure against subjective human extent labels.
- Preserves the useful part of the AI/grid discovery work: very accurate grid orientation, spacing, and homography.
- Keeps the DM workflow focused on "does the projected map line up?" rather than "did the detector perfectly segment the mat?"
- Keeps the future active/projector-camera calibration path compatible with the passive grid detector.

Tradeoffs:

- The internal coordinate frame can extend beyond the physical mat, especially in cropped or off-angle photos.
- The system may allow a DM to place map content outside the mat unless later UI constraints or warnings are added.
- Current evals need to score alignment and usable coverage separately from physical boundary accuracy.
- Real-camera validation is still required before this becomes a product-ready runtime default.
- Optional remote AI grid evidence remains a proof and candidate path, not an MVP dependency.

## References

- Ideal: `docs/ideal.md` - Speed Over Polish, Physical Table First, Robust Manual Control, Calibration Is Product Core
- Spec: `docs/spec.md` - `spec:2.1`, `spec:5.1`, `spec:6.1`, `spec:7.1`
- State/Graph: `docs/methodology/state.yaml`, `docs/methodology/graph.json`
- Stories: `docs/stories/story-003-calibration-algorithm-discovery-evaluation.md`
- Evals: `docs/evals/ai-grid-current-recipe.md`, `test-results/ai-grid-frame-summary-v1/report.md`
- Related decisions: `docs/decisions/adr-001-calibration-architecture.md`

## Open Questions

- How much off-mat map placement should the DM UI allow before warning or clipping?
- Should a later physical-mask feature be used only for warnings, or should it constrain projection?
- How well does the bounded grid-frame approach hold up on fixed-camera video frames from the real projector/camera rig?
- Does active projector-camera calibration make the passive grid-frame extent less important, or does it still need the same internal coordinate frame for source-map placement?
