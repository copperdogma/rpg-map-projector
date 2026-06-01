# ADR-002 Research Prompt - Grid Detection Alignment Frame

Created: 2026-05-31

## Context

The project needs to align a projected battle map to a real 1-inch physical mat quickly enough for live tabletop play. Story 003 explored passive browser detection, gateway-side OpenCV, and optional AI-generated grid evidence over sales photos and real-home mat photos.

The latest real-home lane found that optional AI evidence can align well to the physical grid, but automatic physical mat-boundary ownership remains fragile. Cropped images, off-image corners, shadows, glare, head occlusion, mat curl, and subjective labels make "where should the grid stop?" much less stable than "what coordinate frame does this grid imply?"

The current candidate decision is to use detected grid evidence as an internal alignment frame for snapping and projection, not as an authoritative segmentation of the physical mat.

## What I Need

1. Should the calibration/product path require exact physical mat-boundary detection before projecting a map, or is a bounded aligned grid-frame sufficient for MVP?
2. How should the evals separate grid alignment quality from physical extent or material-boundary quality?
3. What failure modes would justify reopening mat-boundary detection as a required feature?

## Output Format

For each major option, provide:

1. Recommended choice with reasoning
2. Main tradeoffs and failure modes
3. What would need to be true for a different choice to win
4. Evidence or examples
