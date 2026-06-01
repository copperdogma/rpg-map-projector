---
{
  "title": "Labeled Fixture Detector Benchmark",
  "status": "Done",
  "priority": "High",
  "origin": "Story 001 produced a labeled false-input set. The next calibration step needs a bounded scoring harness before more detector tuning or library adoption.",
  "ideal_refs": ["docs/ideal.md"],
  "spec_refs": ["spec:5.1", "spec:6.1", "spec:7.1"],
  "depends_on": [],
  "category_refs": ["spec:5", "spec:6", "spec:7"],
  "compromise_refs": ["B3", "B7"]
}
---

# Story 002: Labeled Fixture Detector Benchmark

## Goal

Turn the saved false-input labels into a repeatable detector benchmark that shows where passive grid detection is accurate, where it is useful only as a correction seed, and where it must refuse to apply a result.

## Background

The current local image set is not representative of final camera frames. Most inputs are product photos with clean lighting, odd crops, packaging, props, or perspective. They are still useful because the grid truth is now labeled manually, including extrapolated corners outside the visible source bitmap.

This story should not chase a 100% pass rate by overfitting to advertising images. Its job is to make detector behavior measurable and visible before deciding whether to keep improving the current browser detector, try OpenCV-style line/geometry methods, or move the primary calibration path toward active markers/fiducials.

## Scope

Build the smallest benchmark that can:

- read `input/map-grid-labels.json`,
- load each labeled source image from the local false-input set,
- run the current detector against each fixture,
- compare detected rows, columns, corners, and candidate/application state against the saved label,
- generate a compact report with pass/fail categories and per-fixture metrics,
- generate overlay screenshots or images that make failure modes easy to inspect,
- optionally run a small deterministic fuzz pass after the baseline benchmark exists.

## Acceptance Criteria

- All labels in `input/map-grid-labels.json` are discovered and included in the report.
- The benchmark records row/column match, mean corner error, max corner error, and whether the detector applied, warned, or failed.
- The benchmark distinguishes at least these outcomes: accepted accurate detection, useful candidate requiring manual correction, rejected/failure, and wrong confident detection.
- The report calls out fixtures with extrapolated ground-truth corners instead of treating off-image corners as invalid.
- Overlay artifacts show the saved label and detector output in different styles.
- Deterministic fuzzing, if included, is reported separately from the hand-labeled base fixtures.
- The story ends with a recommendation: continue current detector tuning, spike a specific OpenCV/fiducial path, or stop passive detector work until real camera frames exist.

## Non-Goals

- Replacing the detector.
- Adopting a new CV library.
- Physical projector/camera calibration.
- Making every sales image pass.
- Expanding the product into a VTT or map library.

## Implementation Plan

- [x] Use a browser-backed benchmark page so the detector runs against the same image/canvas APIs as the workbench.
- [x] Add a benchmark runner that loads saved labels and source images.
- [x] Define detector score metrics and pass/fail categories.
- [x] Produce overlay artifacts for quick visual review.
- [x] Add focused tests for score computation and report generation.
- [x] Run the benchmark against the current labeled set.
- [x] Decide the next detector/calibration direction from the report.

## Current Evidence

- Story 001 produced `input/map-grid-labels.json` with labels for the generated test mat and 11 local false-input battle-mat photos. The corpus now also includes 8 real-home mat photos, for 20 total labeled fixtures.
- Story 001 also established the current detector guardrail: wrong confident projection is worse than refusal, so weak detections should remain candidate-only or failed.
- Scout 002 recommends treating passive grid detection as a helper while considering active calibration with OpenCV-style homography and fiducials for the durable product path.
- Added a browser-backed benchmark page at `/benchmark.html` and a runner command, `npm run benchmark:fixtures`, so the benchmark uses the same browser image/canvas detector path as the workbench.
- Added square-normalized scoring so fixtures with different grid scales are compared by grid-square error instead of raw pixel or image-diagonal thresholds.
- Outcome taxonomy is `auto-accepted-accurate`, `manual-correction-seed`, `safe-refusal`, `wrong-confident`, and `benchmark-error`. Confidence and lattice score remain diagnostics; the hard guardrail is zero `wrong-confident` results.
- The current run wrote `test-results/story-002-fixture-benchmark/report.md`, `report.json`, `benchmark-page.png`, and 20 overlay PNGs under `test-results/story-002-fixture-benchmark/overlays/`.
- Current labeled-fixture baseline after Story 003 added the rough-seed category and the real-home labels: 20 total fixtures, 1 `auto-accepted-accurate`, 0 `manual-correction-seed`, 1 `rough-correction-seed`, 18 `safe-refusal`, 0 `wrong-confident`, 0 `benchmark-error`; application states were 1 applied, 7 warned, and 12 failed.
- The generated test mat is the only accepted accurate detection. The photo fixtures characterize failure modes without creating a pass-rate target. Eleven labels include extrapolated off-image ground truth.
- Deterministic fuzzing was not added in this story because the base benchmark already shows passive detection is weak on the labeled photos. Fuzzing should wait until a detector or active calibration candidate can pass the base fixtures without wrong-confident results.

## Recommendation

Treat passive grid detection as a limited helper. Keep this benchmark as a guardrail, but prioritize an active calibration or fiducial spike before more passive-detector tuning.

## Validation

- `npm run benchmark:fixtures` wrote a full report and 20 overlay artifacts under `test-results/story-002-fixture-benchmark/`.
- Browser QA on `/benchmark.html?run=1` renders the benchmark surface; current e2e coverage includes the benchmark page smoke test.
- `make methodology-compile && make methodology-check`
- `make skills-check`
- `make triage-facts-check`
- `git diff --check`
- `npm run build`
- `npm run test`: 21 unit tests passed.
- `npx playwright test tests/e2e/calibration-workbench.spec.ts`: 15 browser tests passed.

## Work Log

- 20260528-1710 — Created after all current false inputs were labeled in Story 001.
- 20260528-1730 — Started implementation; chose a browser-backed benchmark runner to avoid creating a second image-processing stack in Node.
- 20260528-1735 — Added fixture benchmark scoring, report rendering, browser benchmark page, Playwright runner, local eval registry entry, and overlay artifact output.
- 20260528-1740 — Ran `npm run benchmark:fixtures`: 1 auto-accepted accurate generated fixture, 11 safe refusals on sales photos, 0 wrong-confident detections, 0 benchmark errors.
- 20260529-0040 — Story 003 split near misses into `rough-correction-seed`; the same passive baseline now reports 1 rough seed and 10 safe refusals, still with 0 wrong-confident detections.
- 20260528-1745 — Validated and closed Story 002; the benchmark is now the guardrail for passive detector changes.
