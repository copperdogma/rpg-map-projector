# App Process Reference

This document keeps the major app processes in the order they happen at runtime or in the supporting lab workflow. Keep entries succinct. Use ADRs, eval reports, and stories for the deeper rationale and raw evidence.

## AI-Assisted Grid Alignment Seed

Status: current Story 003 proof path and labeler default seed mode. This is an optional remote-assistance candidate, not an MVP dependency.

Purpose: turn a real-camera battle-mat photo into a grid-aligned coordinate frame. The process intentionally solves alignment first; it does not try to prove the exact physical mat boundary.

1. Capture or select a source photo.
   - Runtime source: fixed gateway camera frame.
   - Lab source: fixture image in the labeler or benchmark corpus.

2. Generate a gridline evidence image.
   - Provider: Grok image generation.
   - Prompt family: `white-grid-exact-copy-no-marks-v1`, with some accepted variants such as `white-grid-solid-only-v6`.
   - Expected output: same crop, aspect ratio, perspective, and geometry as the source photo, but with only printed battle-map gridlines as thin white lines on black.

3. Parse the generated line mask locally.
   - Main script: `scripts/ai-line-graph-lattice.py`.
   - The parser treats the mask as observed grid evidence, groups the line families geometrically, and produces a candidate lattice.
   - The line mask is also used as independent evidence for later dot and lattice validation.

4. Generate intersection-dot evidence only when needed.
   - Provider: Grok image generation.
   - Prompt family: `white-intersection-dots-no-lines-v1`.
   - Expected output: same image geometry, black background, white dots at visible printed-grid intersections only.
   - Dot calls are retried because image-generation output is nondeterministic.

5. Fit dot consensus locally when dot evidence is present.
   - Main script: `scripts/ai-dot-lattice-fit.py`.
   - The fitter clusters candidate intersections, fits visible lattice geometry, validates it against line evidence, and reports support/conflict/readiness diagnostics.

6. Select the best no-label geometry.
   - Summary script: `scripts/ai-grid-hybrid-summary.py`.
   - The current hybrid selector prefers line-graph geometry, but switches to dot consensus when no-label diagnostics show a stronger full-span or high-support fit.
   - Current real-home corpus selection: `6` line-graph cases and `2` dot-consensus cases.

7. Convert the selected lattice into a bounded grid frame.
   - Summary script: `scripts/ai-grid-frame-summary.py`.
   - Preserve the selected homography/alignment.
   - Expand the grid across the source photo instead of using the detected visible patch as the mat boundary.
   - Cap each axis at `100` cells.
   - Trim edge rows or columns whose sampled band has less than `10%` source-photo overlap.
   - Do not use material-aware bright/dark masking in this process; shadows produced false negatives in real-photo tests.

8. Expose the result to the labeler or controller.
   - Labeler endpoint: `/__ai-grid-seed`.
   - Default labeler seed mode: `Bounded image-frame grid`.
   - Other modes remain diagnostic/manual-correction aids: supported visible patch, selected dot extent, wider manual span, and label-sized diagnostic.

9. Use the grid as an internal alignment coordinate frame.
   - The app should project the DM's map onto this coordinate frame.
   - The visible grid overlay is for debugging, calibration, or manual correction.
   - The player-facing default should project the map image, not the detected grid.

Current evidence on the eight `real-map-home-*` proxy photos:

- selected line alignment within `0.15` squares: `99.973%` mean, `99.882%` minimum,
- bounded frame visible-label coverage: `99.95%` mean, `99.598%` minimum,
- old supported/boundary-seeking extents covered only `27.393%` mean and `10.727%` minimum of visible labeled intersections,
- bounded frame seeds stayed within the `100 x 100` cap and avoided fully off-image rows/columns in the current corpus.

Timing notes:

- In the labeler, `Use AI Seed` loads precomputed local artifacts and is effectively immediate.
- Live generation is dominated by model calls, not local parsing.
- Current balanced live candidate: line mask plus three dot samples in parallel, then two more dots only if needed. Replay estimate: about `9.3s` average and `11.7s` max before local fitting.
- Safer streaming balanced candidate: about `8.4s` average and `15.1s` max in replay.
- Fastest safe high-call replay candidate: about `6.6s` average and `10.6s` max, with higher API cost.
- Serial line-first remains diagnostic. It can be fast on easy cases, but hard cases measured around `16-24s`, so it is not the table-speed default.

References:

- Decision: `docs/decisions/adr-002-grid-detection-alignment-frame.md`
- Current recipe: `docs/evals/ai-grid-current-recipe.md`
- Hybrid report: `test-results/ai-grid-hybrid-prompt-ensemble-summary-v1/report.md`
- Grid-frame report: `test-results/ai-grid-frame-summary-v1/report.md`
