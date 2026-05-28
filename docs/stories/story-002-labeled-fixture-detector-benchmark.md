---
{
  "title": "Labeled Fixture Detector Benchmark",
  "status": "Pending",
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

- [ ] Add a benchmark runner that loads saved labels and source images.
- [ ] Define detector score metrics and pass/fail categories.
- [ ] Produce overlay artifacts for quick visual review.
- [ ] Add focused tests for score computation and report generation.
- [ ] Run the benchmark against the current labeled set.
- [ ] Decide the next detector/calibration direction from the report.

## Current Evidence

- Story 001 produced `input/map-grid-labels.json` with labels for the generated test mat and 11 local false-input battle-mat photos.
- Story 001 also established the current detector guardrail: wrong confident projection is worse than refusal, so weak detections should remain candidate-only or failed.
- Scout 002 recommends treating passive grid detection as a helper while considering active calibration with OpenCV-style homography and fiducials for the durable product path.

## Work Log

- 20260528-1710 — Created after all current false inputs were labeled in Story 001.
