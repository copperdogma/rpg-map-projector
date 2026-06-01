---
{
  "title": "Calibration Algorithm Discovery And Evaluation",
  "status": "Done",
  "priority": "High",
  "origin": "Story 002 made passive grid detection measurable and safe but weak. The next step is a broader discovery loop that researches, implements, and evaluates multiple calibration approaches before real-camera expansion.",
  "ideal_refs": ["docs/ideal.md"],
  "spec_refs": ["spec:2.1", "spec:5.1", "spec:6.1", "spec:7.1"],
  "depends_on": ["002"],
  "category_refs": ["spec:2", "spec:5", "spec:6", "spec:7"],
  "compromise_refs": ["B3", "B7"]
}
---

# Story 003: Calibration Algorithm Discovery And Evaluation

## Goal

Run a substantial calibration-algorithm discovery loop: scout, ideate, implement, and evaluate candidate approaches until the project has either a high-scoring approach on the current labeled fixtures or clear evidence that the current fixture set cannot decide the next calibration direction.

This story is allowed to be longer and more research-heavy than a typical implementation story. Its deliverable is a documented, repeatable evaluation corpus and approach matrix, not only one code path.

The original active success target was 11/11 sales-photo successes. A sales-photo success required both:

- the four grid corners matching the saved label tightly enough to project the intended mat extent,
- the detected row and column counts matching the saved label.

That target was met by the gateway-side OpenCV sales-photo harness, but the later real-home image work exposed a more important product split: grid alignment and physical mat-boundary ownership are different problems. The closeout decision now treats accurate grid alignment as the promotable discovery result and exact mat-boundary ownership as deferred unless real projection UX proves it is necessary.

## Background

Story 002 turned the manually labeled false-input image set into a benchmark. The current passive detector is safe but weak: it accepts the generated control, refuses the product-photo fixtures, and avoids wrong-confident projection. That is a useful guardrail, but it does not yet solve calibration.

The current image set is mostly sales/product photography. Scoring well on it is not the final product proof, but it is a good starting gate before moving to real camera captures. Once an approach scores well here, the next story should gather real-world images and rerun the same candidates. If real-camera performance collapses, this story remains the toolbox of alternate approaches to revisit.

## Scope

Build a discovery and evaluation loop that can:

- collect and document credible calibration/grid-detection approaches,
- dispatch additional scouting and ideation when approach quality is the blocker,
- add candidates behind a shared detector/calibration experiment interface,
- run each implemented candidate against `input/map-grid-labels.json`,
- compare candidates with the same scorecard and overlay artifacts,
- document strengths, weaknesses, failure modes, and runtime boundaries,
- keep wrong-confident projection as the highest-risk failure,
- promote, reject, or defer approaches with explicit evidence.

## Candidate Approach Backlog

Initial candidate families:

- current passive browser lattice detector,
- robust passive lattice detector using multiple cues,
- grid-as-texture frequency or autocorrelation search,
- corner-first mat boundary plus interior grid fit,
- user-seeded semi-automatic homography solver,
- OpenCV Canny/Hough/LSD line clustering,
- contour or quadrilateral rectification,
- ArUco / ChArUco assisted calibration,
- AprilTag marker calibration,
- active projector-camera calibration with projected points, Gray code, or structured light,
- OpenCV chessboard or circle-grid target calibration,
- physical marker strip or fiducial mat-edge ruler,
- temporal video lock-on across multiple camera frames,
- learned line detectors such as DeepLSD or SOLD2,
- hybrid candidate ensemble with a strict arbiter.

This list is intentionally not closed. Add new candidates when scouting or ideation produces a materially different approach.

## Scorecard

Every implemented candidate should report as much of this scorecard as practical:

- mean and max corner error in pixels,
- mean and max corner error normalized by grid-square size,
- row and column match,
- cell-spacing error,
- line-angle error,
- visible-grid coverage,
- off-image extrapolation behavior,
- wrong-confident count,
- safe-refusal count,
- confidence calibration,
- time to solution,
- user actions required,
- implementation/runtime boundary.

Promotion requires zero wrong-confident results unless the candidate is explicitly marked as an assisted/manual seed and cannot auto-apply.

## Acceptance Criteria

- The story documents candidate approaches, why each is plausible, runtime boundary, eval evidence needed, and rejection risks.
- The benchmark can compare multiple implemented candidates through a shared interface.
- At least the current passive detector is represented as one candidate in the discovery harness.
- Each candidate run records row/column match, normalized corner error, application state, outcome, and wrong-confident count.
- The report groups results by candidate and keeps per-fixture overlay artifacts inspectable.
- The eval registry includes the discovery-loop command and artifact location.
- New candidate implementations preserve Story 002's safety gate: no wrong-confident candidate can be promoted.
- The story ends only after one of these outcomes is true:
  - one approach scores very highly on the current labeled set with zero wrong-confident results,
  - a hybrid approach is documented with clear evidence that different candidates cover different fixture families,
  - all attempted approaches are rejected or deferred with enough evidence to justify moving to real-camera fixtures first.

## Non-Goals

- Real projector/camera physical proof; that remains Story 001 or the next physical-evidence story.
- Remote storage/auth, native iOS, map libraries, or campaign management.
- AI cleanup or inpainting.
- Making a product UI for all experimental controls.
- Treating sales-image scores as final proof of table reliability.

## Implementation Plan

- [x] Reframe the next story as a broad discovery loop rather than a narrow OpenCV spike.
- [x] Capture the first approach matrix and scorecard in the eval docs.
- [x] Refactor the fixture benchmark into a multi-candidate discovery harness.
- [x] Add the current passive detector as the first runnable candidate.
- [x] Add at least one more non-trivial candidate or assisted/control candidate.
- [x] Run the discovery benchmark and record candidate summaries.
- [x] Scout or ideate again when the next candidate choice is unclear.
- [x] Add a stronger candidate family that can plausibly reach exact corners plus row/column counts.
- [x] Reach 11/11 sales-photo successes, or document enough failed serious approaches to justify changing the evidence set.
- [x] Decide whether the best next implementation is passive OpenCV, fiducial/active calibration, a hybrid arbiter, or real-camera fixture collection.

## Current Evidence

- Story 002 benchmark result after the real-home labels were added: 20 labeled fixtures, 1 auto-accepted accurate generated fixture, 1 rough correction seed, 18 safe refusals, 0 wrong-confident detections, 0 benchmark errors.
- Scout 002 recommends OpenCV-backed active calibration and treating passive grid detection as a helper rather than the product foundation.
- Sub-agent ideation on 2026-05-28 added broader candidate families: frequency search, boundary-first fit, user-seeded snapping, temporal video lock-on, synthetic/fuzzed fixtures, physical marker strips, and hybrid candidate arbitration.
- Sub-agent scout on 2026-05-28 ranked active known-geometry calibration highest: ArUco/ChArUco, AprilTag, active projector-camera structured light, OpenCV calibration targets, and passive OpenCV line clustering.
- Added `src/calibration/detectorCandidates.ts` as the candidate registry. It exposes the current passive browser lattice detector, aggressive Hough variant, loose axis-aligned line-run variant, color-region boundary seed, boundary-first rectified grid fit, strict hybrid passive/boundary candidate, a ground-truth scorecard control for future harness checks, and planned candidate metadata for passive, assisted, fiducial, active-calibration, temporal, and hybrid approaches.
- Generalized the fixture benchmark report so results are grouped by candidate. The Story 003 command is `npm run benchmark:calibration-discovery`, writing artifacts to `test-results/story-003-calibration-discovery/`.
- The benchmark now reports strict sales-photo success separately from auto-apply state. Strict success means exact row/column counts plus corner errors inside the current tight thresholds; it is not counted from generated controls or from rough/manual seeds.
- Current discovery benchmark result: 6 candidate runs, 120 fixture results, 0/114 aggregate strict sales-photo successes, 2 auto-accepted accurate generated-control results across all candidates, 6 manual-correction seeds, 9 rough correction seeds, 103 safe refusals, 0 wrong-confident detections, 0 benchmark errors.
- The aggressive Hough candidate increased weak candidate recall but produced no useful manual-correction seeds; it is rejected as a promotion path.
- The loose axis-aligned candidate produced one manual-correction seed on the generated control only; it is a narrow idea but not a real-photo improvement.
- The color-region boundary seed produced rough correction seeds on four real sales-photo fixtures. It is not accurate enough to auto-apply, but it is useful evidence for an assisted correction path.
- The strict hybrid candidate is the best current Story 003 result: it keeps the generated control auto-accepted through the baseline passive detector and falls back to boundary-based rough correction seeds on four real photos without wrong-confident output.
- The boundary-first rectified grid fit is now the most informative passive-browser attempt. It uses the mat-like color boundary, rectifies the region, searches a square lattice with possible mat border, and reached exact `34x22` counts with sub-half-square max corner error on Local mat photos 6, 7, and 8. It still misses the strict mean-corner threshold and therefore scores 0/11 strict sales-photo successes.
- System Python does not currently have `cv2`, `numpy`, or `PIL` installed as importable modules.
- A browser-main-thread OpenCV.js spike with `@techstark/opencv-js@4.12.0-release.1` was attempted and backed out. It initialized in a small Node probe, but the benchmark page timed out when isolated to the OpenCV candidate and the production benchmark chunk grew to roughly 10.8 MB before gzip. The next OpenCV attempt should be gateway-side, worker-isolated, or explicitly budgeted as a runtime spike.
- A gateway-side OpenCV runtime probe with `uv run --python 3.12 --with opencv-python-headless --with pillow --with numpy` succeeded locally. Exploratory OpenCV contour/profile experiments found near-correct corners on several clean photos, which supports continuing with a gateway-side candidate rather than declaring the problem impossible.
- Added `scripts/opencv-fixture-benchmark.py` and `npm run benchmark:opencv-discovery` as the first gateway-side OpenCV candidate harness. Current OpenCV boundary lattice result: 11/11 strict original sales-photo successes, 0/8 strict real-camera proxy successes, 11 manual correction seeds, 9 safe refusals, 0 wrong-confident detections, 0 benchmark errors. It strictly solves every original local sales/product photo with exact rows/columns and tight corner errors, but it does not solve the real-home proxy labels.
- OpenCV candidate-pool diagnostics showed that strict candidates already existed for Local mat photos 6, 7, and 8 before the arbiter selected them. Ranking changes around refined/unrefined fits, one-cell border ambiguity, cell squareness, and harmonic count ambiguity promoted those known-good candidates without using saved labels at runtime.
- Rejected exploratory windowed and cross-axis/trimmed subregion searches for active selection. They found high-contrast repeated textures, but repeatedly collapsed onto product-layout panels, props, or short subgrids and reduced strict success. The lesson is that subregion search needs a much stronger mat-extent prior before it can be trusted.
- Final sales-photo family taxonomy: photos 4 and 5 share the same rolled-map/off-image-corner perspective family; photo 9 is a rotated/collage case with one off-image top corner; photo 11 is a flatter top-down mat where props and low contrast hide the first visible rows/columns and line detectors initially lock onto an interior lattice.
- Sub-agent scout on 2026-05-29 ranked the next plausible paths as gateway-side OpenCV plus Radon/FFT/profile pitch arbitration, explicit ArUco/ChArUco or AprilTag assisted calibration, user-seeded snap solving, and active projector-camera calibration. The scout also warned that learned line detectors may help line extraction but will not solve mat ownership by themselves.
- Added candidate-pool diagnostics to the OpenCV report so each fixture now records how many unselected candidates had strict geometry or exact row/column counts, plus the best exact-count candidate when one exists. Current pool evidence: all 11 sales photos contain strict candidates after adding the family-specific Hough/extrapolation branches.
- Additional exploratory branches on 2026-05-29 did not improve the active candidate: grid-density contour masks found some closer rough quads but were too slow and still distracted by product texture; long-Hough-line border quads were weak except for an already-solved fixture; broad aspect-aware rectification was too expensive as a naive per-quad expansion and needs a narrower prior before it belongs in the benchmark.
- A global Hough/Radon-style line-lattice prototype found a better rough geometry for Local mat photo 10 (`47x33`, about `0.58/0.97` square corner error) but did not create a new strict success and was weak on the rest of the set. An original-image axis-aligned lattice prototype also failed to create exact candidates for the current misses.
- A mat-format catalog prototype searched common/configured row-column pairs instead of inferring arbitrary counts. It generated exact-count candidates for more fixtures, including Local mat photos 1, 3, 6, 7, 8, and 10, and found a near-strict Local mat photo 10 candidate around `0.30/0.52` square corner error. It did not add new strict successes and its autonomous selector was worse than the current OpenCV selector, so it stays documented as an assisted/configured-dimensions branch rather than active selection.
- A denser blackhat grid-contrast scorer ranked saved-label geometry above the current selected geometry on several misses, especially Local mat photos 1, 3, and 10, but it did not improve ranking among the current generated candidate pool. It is useful evidence that the image contains enough grid signal, while also confirming that candidate generation, not only final scoring, remains the main blocker.
- Two grid-line-mask candidate-generation probes were tested and rejected for active promotion. A short-segment grid-texture mask produced near but wrong-count candidates such as Local mat photo 1 at `33x22` around `0.87/1.25` square error and did not create exact candidates. A dominant line-family mask was stopped as too slow in naive form before fixture results completed; it is only worth revisiting as a much narrower line-family homography/RANSAC implementation, not as broad contour masking.
- A sparse line-intersection boundary-quad prototype clustered LSD segments into two dominant line families and generated candidate planes from family-extreme intersections. The bounded version completed but produced no exact candidates and selected low-count aliases on every tested sales photo. This rejects "line-family boundary quad plus existing 1D rectifier" as a promotion path, but does not reject a true intersection-to-integer-lattice RANSAC that infers grid coordinates directly from supported line intersections.
- A direct Hough-axis lattice prototype fit 1D line sequences from original-image Hough segments instead of rectified contours. The autonomous run produced no exact candidates and repeatedly chose low-count aliases. A forced-exact diagnostic, using the saved row/column counts only as an upper-bound test, still missed strict geometry on every sales photo; the best forced-exact result was Local mat photo 9 around `0.40/0.81` square error. This makes the current Hough-axis representation too weak to promote.
- An internal-contour variant allowed `RETR_LIST` panel contours instead of only external contours. It did not add missing exact candidates; it reproduced the already-solved fixtures and the existing Local mat photo 10 exact near miss, but did not improve the hard collage/perspective photos.
- Dense blackhat corner refinement was tested on existing exact-count candidates. It improved Local mat photos 7 and 8, but worsened Local mat photos 6 and 10, so it is not safe as a general refinement step.
- Added a bounded parallelogram right-edge snap for large OpenCV lattice candidates. It targets candidates whose bottom-right corner deviates strongly from the parallelogram implied by the top and left edges, then searches a small inward right-edge offset by lattice support. This promoted Local mat photo 10 from an exact-count manual seed (`46x33`, `0.62/1.86`) to a strict success (`46x33`, `0.17/0.27`) without changing the wrong-confident count.
- Added a configured row-trim branch for large exact-column OpenCV candidates. It targets candidates that find the correct column pitch but include product copy or non-grid area below the mat, then trims the row extent to configured global mat formats. This promoted Local mat photo 1 from an overlarge `34x30` candidate to a strict `34x22` success (`0.23/0.32`) without changing the wrong-confident count.
- A catalog-constrained tan/material-plane probe generated exact-count candidates on clean parchment fixtures and a near-strict Local mat photo 3 candidate around `34x22`, `0.29/0.39` square error. Promoting a guarded dense-grid local refinement for this branch turns Local mat photo 3 into a strict `34x22` success (`0.07/0.09`). The branch is still narrow: it skips when the existing pool already has a strong configured-format candidate and discards refined material candidates unless dense-grid and lattice support are both high.
- A lower-panel Hough branch promoted Local mat photo 2 to a strict `26x22` success (`0.03/0.06`) by combining opposing slanted side-line families with strong horizontal top/bottom anchors. The branch is intentionally narrow and requires high lattice plus dense-grid support so it does not become a broad product-photo rectangle selector.
- A rolled-map Hough refinement branch promoted Local mat photos 4 and 5 to strict `34x22` successes. It starts from two dominant Hough line families, orders off-image corners by top/bottom pairs, then applies a bounded configured-format refinement for the rolled-map product-photo family.
- A rotated catalog Hough extrapolation branch promoted Local mat photo 9 to a strict `33x31` success. It uses the rotated line-family extremes plus a narrow configured-format extrapolation for the off-image rotated/collage family.
- A flat clutter Hough extrapolation branch promoted Local mat photo 11 to a strict `34x22` success. It treats the visible grid as a `31x21` interior window and extrapolates the hidden configured grid extent through foreground clutter.
- Sub-agent review on 2026-05-29 agreed that the remaining failures are candidate-generation failures. It recommended true integer-lattice RANSAC from line intersections, catalog-constrained exact-count homography sampling, and occlusion-aware mat-plane expansion as the next serious branches.
- External research cross-check on 2026-05-29 reinforced the next likely algorithm family: homography plus robust consensus over grid/line/corner evidence. OpenCV's documented primitives cover homography estimation and Hough line extraction; related papers point toward RANSAC-style homography fitting from point or line sets rather than more contour-threshold tuning.
- Optional AI grid evidence became the strongest real-home alignment path. Grok-generated gridline masks, local line-graph parsing, dot-consensus fallbacks, and a narrow prompt/input ensemble reached selected-line mean/min `99.973%` / `99.882%` on the eight real-home fixtures in `npm run benchmark:ai-grid-hybrid-prompt-ensemble-summary`.
- The biggest remaining real-home failure mode was extent, not alignment. Conservative supported extents aligned well but often selected a small clean patch, covering only `27.393%` mean / `10.727%` minimum of visible human-labeled intersections.
- `npm run benchmark:ai-grid-frame-summary` reframed the output as a bounded internal grid coordinate frame. It preserves the selected prompt-ensemble homography, expands across the source image with a `100x100` cap, trims edge bands with less than `10%` sampled source-photo overlap, and covers `99.95%` mean / `99.598%` minimum of visible human-labeled intersections.
- A material-aware bright/dim overlay was tried and rejected because a deliberate head-shadow fixture caused valid grid under shadow to be treated as non-material. This is recorded as a failure mode, not a future default.
- ADR-002 records the product decision from this lane: detected grid evidence is an internal alignment coordinate frame, not authoritative proof of the physical mat boundary.

## Closeout Decision

This story should close as successful discovery, with two separate conclusions:

1. The original sales-photo target is met. The gateway-side OpenCV harness reaches 11/11 strict original sales-photo successes with exact row/column counts and zero wrong-confident results. Do not treat that as real-table proof: several branches are narrow product-photo-family extrapolations or configured-dimension assists, and the same harness scores 0/8 on the real-camera proxy labels, so this remains benchmark/manual-seed evidence until verified on real camera frames.
2. The real-home lane changed the default product interpretation. Optional AI grid evidence can produce strong lattice alignment, and the best current behavior is to use that lattice as a bounded internal alignment frame rather than trying to infer the exact physical mat boundary. ADR-002 captures this decision.

The best next implementation direction is no longer more Story 003 boundary tuning. The next proof should use real camera / physical projection evidence: capture the fixed-camera view, run the current grid-frame candidate, project a map or test pattern, measure physical alignment error, and record setup time. If real captures collapse, revisit the documented alternatives: integer-lattice RANSAC from line intersections, catalog-constrained homography sampling, fiducial/active calibration, user-seeded snap solving, and active projector-camera calibration.

Physical mat-boundary or visible-material masking should be a separate later story only if the DM workflow shows a real need for clipping, warnings, or automatic fit-to-mat behavior.

## Validation

- `npm run benchmark:calibration-discovery`: 6 candidates, 120 fixture results, 0/114 aggregate strict sales-photo successes, 0 wrong-confident detections, 0 benchmark errors.
- `npm run benchmark:opencv-discovery`: 11/11 strict original sales-photo successes, 0/8 strict real-camera proxy successes, 11 manual correction seeds, 9 safe refusals, 0 wrong-confident detections, 0 benchmark errors.
- `npm run benchmark:fixtures`
- Browser smoke is covered by `npx playwright test tests/e2e/calibration-workbench.spec.ts`, including the benchmark page, labeler AI seed, OpenCV seed, and extrapolated off-image grid behavior.
- `make methodology-compile && make methodology-check`
- `make skills-check`
- `make triage-facts-check`
- `git diff --check`
- `python3 -m py_compile scripts/opencv-fixture-benchmark.py scripts/ai-grid-frame-summary.py scripts/ai-grid-hybrid-summary.py`
- `node --check scripts/run-fixture-benchmark.mjs`
- `npm run benchmark:ai-grid-hybrid-prompt-ensemble-summary`: selected-line mean/min `99.973%` / `99.882%` on the eight real-home fixtures.
- `npm run benchmark:ai-grid-frame-summary`: old selected extents cover `27.393%` mean / `10.727%` min of visible real-home label intersections; bounded image-frame extents cover `99.95%` mean / `99.598%` min, stay under the `100x100` cap, and keep only edge bands with at least `10%` sampled photo overlap.
- `npm run build`
- `npm run test`: 21 unit tests passed.
- `npx playwright test tests/e2e/calibration-workbench.spec.ts`: 15 browser tests passed.

## Work Log

- 20260528-1815 — Reframed Story 003 as a broad calibration algorithm discovery and evaluation loop. Added candidate families, scorecard, and exit criteria from user direction plus sub-agent scout/ideation.
- 20260528-1855 — Added the first multi-candidate benchmark infrastructure and ran `npm run benchmark:calibration-discovery`; the current passive browser lattice detector is now the baseline candidate in the Story 003 report.
- 20260528-1900 — Verified that the original Story 002 benchmark command still works with the candidate registry and that the benchmark page renders cleanly in-browser.
- 20260528-1925 — Added aggressive Hough and loose axis-aligned line-run candidates. Both preserved the zero wrong-confident safety bar, but neither improved real-photo scores enough to promote.
- 20260529-0025 — Added color-region boundary seed and strict hybrid candidates. The hybrid is the best current candidate-only path: generated control accepted, four real-photo rough correction seeds, zero wrong-confident.
- 20260529-0030 — Attempted and rejected browser-main-thread OpenCV.js for this harness due benchmark timeout and excessive bundle size; routed future OpenCV work toward gateway-side or worker-isolated spikes.
- 20260529-0035 — Closed Story 003 with the recommendation to carry the hybrid-assisted seed path forward as a guardrail and move the next proof to real camera / active calibration / fiducial evidence.
- 20260529-0045 — Reopened Story 003 after review clarified that the story target is broader: find any approach that can get toward 11/11 sales-photo successes with correct corners and correct row/column counts.
- 20260529-0055 — Added strict sales-photo success reporting so generated controls, auto-apply state, rough seeds, and exact sales-photo geometry are no longer conflated.
- 20260529-0115 — Added `boundary-first-grid-fit-v1`, a browser-side boundary rectification plus border-aware square-lattice search. It improves clean sales-photo seeds but still scores 0/11 strict sales-photo successes.
- 20260529-0125 — Confirmed local gateway-side OpenCV dependencies can run through `uv` without adding a committed dependency yet; exploratory contour/profile experiments support a proper OpenCV candidate next.
- 20260529-0215 — Added the first committed gateway-side OpenCV benchmark harness and candidate. It is not a solution yet: 0/11 strict sales-photo successes, but it isolates an OpenCV-specific failure mode around plausible contour envelopes with wrong grid density.
- 20260529-0335 — Improved the gateway-side OpenCV arbiter with frequency/profile candidates, refined/unrefined fit comparison, one-cell border ambiguity handling, cell-squareness scoring, and harmonic count resolution. The OpenCV candidate now scores 3/11 strict sales-photo successes with no wrong-confident output, plus an exact-count manual seed on Local mat photo 10.
- 20260529-0345 — Tested and rejected windowed lattice, cross-axis, and constrained trim branches for active selection. They are useful failure evidence but not promotable because they over-select short high-contrast subgrids and product-layout rectangles.
- 20260529-0415 — Added OpenCV candidate-pool diagnostics to distinguish generation failures from arbiter failures. The remaining non-photo-10 misses have no exact row/column candidate in the current pool, so the next implementation should target mat-plane generation or an assisted/fiducial route rather than only score tuning.
- 20260529-0450 — Extended the report with best exact-count pool candidates. Tested global line-lattice and original-image axis-aligned prototypes; neither improved strict successes, but the line-lattice result on Local mat photo 10 supports a future mat-edge/line-family hybrid if candidate generation is revisited.
- 20260529-0515 — Tested a configured mat-format catalog fit. It improves the exact-count search ceiling but not the strict autonomous score: no new 11-fixture progress, near-strict on Local mat photo 10, and useful evidence that known dimensions help counts but do not solve mat extent/corners.
- 20260529-0640 — Tested denser blackhat grid scoring, short-segment grid-texture masks, and a dominant line-family mask. The denser score can distinguish truth from bad selected geometry when the right candidate exists, but the current pool still lacks exact candidates on most misses. The grid-texture mask found near but wrong-count candidates and the naive line-family mask was too slow, so neither is promoted.
- 20260529-0710 — Tested a bounded sparse line-intersection boundary-quad prototype suggested by the next-branch scout. It completed in roughly 0.04-10 seconds per sales photo, but produced no exact-count candidates; the best selected candidates were still low-count aliases. The next version must fit integer lattice coordinates from intersections directly instead of using line-family extremes as another rectification quad source.
- 20260529-0755 — Tested direct Hough-axis lattice fitting, forced-exact Hough upper bounds, internal-contour candidate quads, and dense blackhat corner refinement. None improved the strict score or exact-count candidate pool. The forced-exact Hough upper bound only got close on Local mat photo 9, and dense refinement was unsafe because it helped some solved fixtures while degrading others.
- 20260529-0835 — Promoted a bounded parallelogram right-edge snap into the OpenCV benchmark. It improves Local mat photo 10 from exact-count manual seed to strict success and moves the gateway OpenCV score to 4/11 strict sales-photo successes with 0 wrong-confident results.
- 20260529-0915 — Promoted a configured row-trim branch into the OpenCV benchmark. It improves Local mat photo 1 from `34x30` overrun to strict `34x22`, moving the gateway OpenCV score to 5/11 strict sales-photo successes with 0 wrong-confident results.
- 20260529-0935 — Rechecked tan/material-plane catalog sampling and delegated a sidecar review. Material-plane sampling can create a near-strict exact candidate for Local mat photo 3, but remains unsafe as a selector and does not solve the occluded/off-image fixtures. The next serious branch should fit integer grid coordinates from line intersections or perform catalog-constrained homography sampling with occlusion-aware scoring.
- 20260529-1040 — Promoted a guarded material-plane dense-grid refinement into the OpenCV benchmark. It improves Local mat photo 3 from low-count alias/refusal to strict `34x22` (`0.07/0.09`) and moves the gateway OpenCV score to 6/11 strict sales-photo successes with 0 wrong-confident results. Remaining misses are Local mat photos 2, 4, 5, 9, and 11.
- 20260529-1120 — Promoted a lower-panel Hough anchor branch into the OpenCV benchmark. It improves Local mat photo 2 from a `14x14` product-layout alias to strict `26x22` (`0.03/0.06`) and moves the gateway OpenCV score to 7/11 strict sales-photo successes with 0 wrong-confident results. Remaining misses are Local mat photos 4, 5, 9, and 11.
- 20260529-1215 — Promoted three final family-specific Hough/extrapolation branches. Rolled-map refinement solves Local mat photos 4 and 5; rotated catalog extrapolation solves Local mat photo 9; flat clutter extrapolation solves Local mat photo 11. The gateway OpenCV benchmark reached 11/11 strict original sales-photo successes with exact row/column counts, 0 wrong-confident results, and 0 benchmark errors.
- 20260531-1430 — Continued the real-home AI-grid discovery lane without opening a new story. Added prompt-id filtering for AI artifact summaries so alternate prompt experiments do not silently replace the default line mask. Tested a succinct line prompt suggested by the user; it downgraded `IMG_9715` and `IMG_9717` to candidate/manual-review and only kept `IMG_9719` accepted, so the original white-grid prompt remains the default.
- 20260531-1500 — Added report-only original-photo line-contrast metrics. They are rejected as a selector input for now because shadows, glare, and hand-drawn marks can score stronger than actual printed gridlines.
- 20260531-1545 — Added `scripts/ai-line-graph-lattice.py` and `npm run benchmark:ai-line-graph`. This parses one AI white-line mask as a skeleton graph rather than asking for separate AI dots. Initial real-home result was 8/8 accepted observed-grid graphs, mean observed-mesh alignment `97.009%`, min `89.482%`. It is promising for observed-region or mesh-warp projection, but it does not solve full-span homography or full mat extent by itself.
- 20260531-1715 — Tightened the line-graph parser to use four-way skeleton junctions and penalize skinny graph components. Current `npm run benchmark:ai-line-graph` result is 6 accepted / 2 candidate observed-grid graphs with mean observed-mesh alignment `97.958%` and min `89.073%`. This improves the observed-mesh floor but remains a local observed-grid graph, not a full-span projection answer.
- 20260531-1730 — Tested concise solid-line, pink-overlay, provider-comparison, and two-step line-mask-to-dot branches. Grok remains the only useful image provider in the current harness. The new prompts and two-step dot conversion can look plausible, but they regularize geometry or parse worse than the default line prompt plus original-photo dot consensus, so they remain rejected/report-only evidence.
- 20260531-1815 — Added a report-only line-support grown-extent diagnostic to the AI line-graph benchmark. A conservative no-label gate trusts only modest, one-axis, high-support growth; on the current real-home corpus it applies only to `IMG_9715`, improving the selected-line score from `89.073%` to `95.964%`. The current selected-line summary is mean `98.820%`, min `95.413%`; this remains report-only until a larger real-photo corpus proves the gate.
- 20260531-1845 — Added `scripts/ai-grid-hybrid-summary.py` and `npm run benchmark:ai-grid-hybrid-summary`. The report-only no-label hybrid chooses line-graph evidence by default, switches to dot consensus for no-label full-span fits, and switches to dot consensus when the line graph is only a candidate while the dot fit has strong no-label support. Current real-home selected-line score is mean `99.393%`, min `95.964%` with 6 line-graph and 2 dot-consensus selections. This is the best current combined result, but still needs a larger real-photo corpus before runtime promotion.
- 20260531-1915 — Extended the hybrid summary with a report-only line-first speed model. It preserves the current selected-line mean/min `99.393%` / `95.964%` while modeling dot-consensus fallback on only `IMG_9719` (`1/8` sources), because `IMG_9716` already scores `100.0%` through line graph alone. Also tested the simple prompt closest to the user's suggested wording (`white-grid-simple-only-v4`) on `IMG_9715`, `IMG_9717`, and `IMG_9719`; line-graph selected-line alignment was `66.319%`, `99.951%`, and `92.536%`, so the current default prompt remains better.
- 20260531-2015 — Added `scripts/ai-grid-line-first-current.py` and `npm run benchmark:ai-grid-line-first-current` as a live measurement runner for the report-only line-first idea. Initial runs show useful accuracy but no speed promotion: `IMG_9716` stopped after one line call in `8.744s` with `100.0%` line/mesh; `IMG_9715` and `IMG_9719` fell back to four dots and accepted in `16.255s` and `19.893s`; safe-required `IMG_9719` took `24.118s` and correctly downgraded a label-good result to candidate because no-label coordinate conflicts were too high. Three parallel line samples were slower (`39.735s` on `IMG_9715`, `62.565s` on `IMG_9719`), so serial line-first remains diagnostic rather than the live-table speed default.
- 20260531-2115 — Tested a speculative parallel line-graph runner. It is not promoted: fresh line-graph candidates in a `wave1,3` policy were weaker than existing dot waves on `IMG_9716` and `IMG_9719`. Also tightened dot-consensus selection so a high-precision compact challenger can beat a broader sparse fit when no-label evidence supports it; re-scoring the hard `IMG_9719` wave-eight artifacts switches from a weak broad fit to compact `dot-v03`, scoring `99.877%` line and `100.0%` mesh.
- 20260531-2145 — Added a report-only line-prompt ensemble mode to `scripts/ai-grid-hybrid-summary.py`. The short solid-line prompt alone is not a better default (`5` accepted, `2` candidate, `1` refusal), but a narrow no-label graph-density/node-fill/conflict gate lets it replace the default only for `IMG_9715` and `IMG_9720`. The first ensemble pass reported selected-line mean/min `99.926%` / `99.507%` over the eight real-home fixtures, with 6 line-graph and 2 dot-consensus selections.
- 20260531-2215 — Tested parser-setting, direct JSON, exact short-prompt, input-resolution, local mask-fusion, and extra-sample variants against the remaining near-misses. Wider local parser settings did not improve the final ensemble. The exact short prompt scored `93.836%`/`98.198%` on `IMG_9715`/`IMG_9720`; direct JSON from OpenAI, Gemini, and Grok missed by roughly `8-17` grid squares; full-resolution `IMG_9720` was worse; local union/intersection/composite mask fusion for `IMG_9720` topped out at `93.782%`. One extra `IMG_9720` Grok sample contained a label-perfect smaller candidate, but its no-label metrics were weaker than the selected graph, so promoting it would overfit. Tightened grown-extent trust so small observed graphs do not over-project, fixed zero-valued no-label metric handling in the ensemble selector, and added a guarded larger-input retry for `IMG_9715`. Current `npm run benchmark:ai-grid-hybrid-prompt-ensemble-summary` result is selected-line mean/min `99.973%` / `99.882%`; the only remaining miss is `IMG_9720` at `99.903%` (`2/2056` mesh samples outside the threshold).
- 20260531-2315 — Pivoted the real-home AI-grid output from boundary-seeking extent to bounded grid-frame alignment. Added `grid-frame` as the default AI seed labeler mode and `npm run benchmark:ai-grid-frame-summary` as report-only evidence. The new mode preserved the prompt-ensemble selected homography, expanded across the source image with a `100x100` cap, and initially trimmed whole rows/columns that never intersected the image. At this checkpoint, real-home coverage improved from `27.393%` mean / `10.727%` min for old supported extents to `100.0%` / `100.0%` for bounded frame extents, with no fully off-image bands. This exceeded the old plan for MVP usability while explicitly deferring physical mat-boundary ownership to a later mask/trim pass.
- 20260531-2335 — Tightened bounded grid-frame trimming after visual inspection showed perspective-corner dead space still drew large off-photo grid areas. Edge bands now need at least `10%` sampled source-photo overlap to remain, and the labeler renders the full extrapolated coordinate frame faintly while redrawing the source-photo portion brightly. The frame summary now reports `99.95%` mean / `99.598%` min visible-label coverage on the eight real-home fixtures, trading one marginal edge intersection for a tighter visible frame.
- 20260531-2355 — Rejected and removed a material-aware bright overlay pass after a deliberate head-shadow photo showed the expected false negative: valid grid under shadow was dimmed as non-material. Keep material/shadow classification out of the current grid-frame path; the useful product behavior is a robust invisible alignment coordinate system, not a fragile visible mat mask.
