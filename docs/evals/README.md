# Evals

The first automated eval surface is the labeled fixture benchmark:

- `npm run benchmark:fixtures` writes Story 002 passive detector guardrail artifacts to `test-results/story-002-fixture-benchmark/`.
- `npm run benchmark:calibration-discovery` writes Story 003 candidate-comparison artifacts to `test-results/story-003-calibration-discovery/`.
- `npm run benchmark:opencv-discovery` writes the gateway-side OpenCV candidate artifacts to `test-results/story-003-opencv-discovery/`.
- `npm run detect:opencv-real-home` writes unscored real-home photo overlays to `test-results/story-001-real-home-opencv-dry-run/`.
- `npm run benchmark:opencv-real-home` writes scored real-home OpenCV artifacts to `test-results/story-001-real-home-opencv-scored/`.
- `npm run benchmark:ai-grid-current` re-scores the current optional AI-assisted grid evidence artifact set and writes selected visible-lattice reports to `test-results/ai-dot-lattice-fit-selected-v2/`.
- `npm run benchmark:ai-grid-hybrid-summary` combines the current dot-consensus and line-graph reports with a report-only no-label hybrid gate and a line-first speed model; it writes to `test-results/ai-grid-hybrid-summary-v1/`.
- `npm run benchmark:ai-line-graph-solid` replays the short solid-line Grok prompt through the observed-grid graph parser; it writes to `test-results/ai-line-graph-lattice-solid-v6-summary/`.
- `npm run benchmark:ai-line-graph-solid-w1600` replays the short solid-line Grok prompt generated from the larger working-input retry through the observed-grid graph parser; it writes to `test-results/ai-line-graph-lattice-solid-w1600-summary/`.
- `npm run benchmark:ai-grid-hybrid-prompt-ensemble-summary` combines the default and short solid-line graph reports with the dot-consensus report through a narrow no-label prompt-ensemble selector; it writes to `test-results/ai-grid-hybrid-prompt-ensemble-summary-v1/`.
- `npm run benchmark:ai-grid-frame-summary` compares the old boundary-seeking/supported extents against ADR-002's bounded grid-alignment frame; it writes to `test-results/ai-grid-frame-summary-v1/`.
- `npm run benchmark:ai-grid-line-first-current` runs a live line-first measurement policy: line mask and line-graph parse first, then dot fallback only when needed; it writes to `test-results/ai-grid-line-first-current/`.
- `npm run benchmark:ai-grid-parallel-current` runs the current Grok white-line plus dot retry recipe against one source image with live parallel API calls and writes to `test-results/ai-grid-parallel-current/`. Pass `-- --waves 2,1,2` to test the lower-call economy schedule.
- `npm run benchmark:ai-grid-parallel-hybrid` runs an experimental live policy with two first-wave dot samples, a skeletonized line-mask accept gate, and a three-dot fallback wave; it writes to `test-results/ai-grid-parallel-current/`.
- `npm run benchmark:ai-line-junction` tests whether one AI white-line mask can replace AI dots by extracting local junctions; it writes to `test-results/ai-line-junction-probe-v1/`.
- `npm run benchmark:ai-line-lattice` tests a true ordered line-family/intersection fitter over one AI white-line mask; it writes to `test-results/ai-line-lattice-ransac-v1/`.
- `npm run benchmark:ai-line-skeleton` tests a no-extra-AI-call path that skeletonizes one AI white-line mask and extracts branch-point junctions; it writes to `test-results/ai-line-skeleton-junction-probe-v1/`.
- `npm run benchmark:ai-line-graph` tests a no-extra-AI-call path that parses one AI white-line mask as a local observed grid graph; it writes to `test-results/ai-line-graph-lattice-v1/`.
- `npm run benchmark:ai-family-stripes` tests generated single-family stripe masks; it writes to `test-results/ai-mask-lattice-probe-family-stripes-v2-full/`.
- `npm run benchmark:ai-family-pair` directly tests paired one-family masks by intersecting Hough clusters from less-steep and more-steep generated stripe images; it writes to `test-results/ai-family-pair-lattice-v1/`.
- `npm run benchmark:active-fiducial-sim` runs a synthetic active-calibration comparison between projected coded fiducials, symmetric/asymmetric projected circle grids, projected ChArUco, one-frame composite fiducial/circle patterns, static and target-adapted two-frame fiducial-plus-circle refinement, full-surface holdout error, point-level lens undistortion stress, projector-distortion stress, photometric preflight normalization, and speed-aware one-frame/two-frame recommendations; it writes to `test-results/projected-fiducial-calibration-sim/`.

Physical evidence is still required before claiming product calibration success: projected alignment error, setup time, covered mat area, and table usability from Story 001 or a follow-up real-camera story.
