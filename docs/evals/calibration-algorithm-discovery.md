# Calibration Algorithm Discovery Eval

This document is the working scorecard and candidate matrix for Story 003.

The purpose is to compare calibration and grid-detection approaches against the same labeled fixtures before moving to real camera frames. High scores on the current sales/product image set are useful, but they are not final proof of table reliability.

## Evaluation Rule

Wrong-confident alignment is the highest-risk failure. A candidate that refuses weak inputs can remain useful. A candidate that auto-applies a visibly wrong grid should not be promoted.

Promotion candidates must report:

- zero wrong-confident results,
- strict sales-photo success count,
- high auto-accepted accurate count or clearly useful manual-seed count,
- normalized corner error in grid squares,
- row and column accuracy,
- failure mode notes,
- runtime boundary and setup burden.

## Shared Metrics

| Metric | Reason |
|---|---|
| Mean corner error in squares | Compares fixtures with different pixel scales. |
| Max corner error in squares | Catches a single bad extrapolated corner. |
| Row/column exact match | Verifies source grid extent, not only rough perspective. |
| Application state | Separates auto-apply, warning candidate, and refusal. |
| Wrong-confident count | Blocks promotion when projection would be misleading. |
| Safe-refusal count | Acceptable when a candidate cannot make a reliable call. |
| Manual-seed count | Shows whether a rejected candidate still saves user effort. |
| Rough-seed count | Separates near-enough correction starts from total refusals. |
| Off-image corner handling | Required because real captures may crop off mat corners. |
| Time to solution | Matters for live table speed. |
| User actions required | Distinguishes automatic, assisted, and manual workflows. |

## Real-Camera Scoring Interpretation

Real-camera labels are a human judgment of the visible, usable grid region. They are not an exact mathematical truth for the physical mat's outer boundary.

Do not treat a one-to-one match to the manually labeled outer quadrilateral as the only valid success criterion. A detector may be product-useful when it chooses a slightly smaller or larger usable grid, especially when a mat edge curls, the camera crops off corners, foreground objects hide rows or columns, glare erases a border, or the labeler's chosen stopping point is itself subjective.

The stricter corner/row/column score remains useful as a regression guard, but real-camera promotion should also report:

- interior grid-line alignment inside the overlapping usable region,
- whether the detected lattice pitch and angle match the labeled lattice,
- visible-grid coverage instead of only outer-corner agreement,
- whether an extent mismatch is conservative, expansive, or locked onto the wrong repeated pattern,
- whether the result is good enough as an editable seed even when its outer grid extent differs from the label.

Wrong lattice ownership is still a hard failure: snapping confidently to a prop, packaging panel, table edge, inset patch, or small interior subgrid should remain rejected even if the detected lines look regular.

Lens distortion is a detection risk, not automatically a projection failure. The physical mat is flat, but the camera measurement can bend straight grid lines. Keep the current passive detector benchmark-only until real-camera evidence shows whether camera undistortion, active calibration targets, fiducials, or a denser projector-camera mapping are needed.

## Candidate Matrix

| Candidate | Runtime Boundary | Why It Might Work | Evidence Needed | Reject If |
|---|---|---|---|---|
| Current passive browser lattice | Browser TypeScript/canvas | Already integrated; combines line families, spacing, and lattice gates. | Baseline fixture report and overlay artifacts. | It remains safe but cannot produce useful seeds. |
| Robust passive lattice ensemble | Browser or OpenCV.js/Python | Combines line segments, orientation histograms, vanishing consistency, coverage, and plausibility. | Better fixture scores without wrong-confident increases. | It locks onto packaging, subsets, shadows, or product-photo artifacts. |
| Grid-as-texture frequency search | Browser WASM, OpenCV, or Python numeric stack | Repeating grid texture may be detectable even when lines are faint. | Pitch/orientation error and projected lattice fit. | It confuses mat weave, compression, or paper texture for the 1-inch grid. |
| Boundary-first plus interior grid fit | Browser or OpenCV | Mat outline can constrain the playable region before fitting lines. | Boundary accuracy, off-image extrapolation, row/column accuracy. | It overfits sales-photo borders or latches onto packaging/table edges. |
| Boundary-first rectified grid fit | Browser TypeScript/canvas | Rectifies the mat-like color boundary and searches a square lattice with a possible mat border. | Strict sales-photo count and near-miss fixture artifacts. | It only solves clean product photos or chooses low-count/double-count lattices. |
| User-seeded semi-automatic solver | Browser TypeScript/canvas | One or two user gestures may turn weak detection into reliable snapping. | User actions, elapsed time, final corner error. | It becomes full manual labeling in disguise. |
| OpenCV line clustering | OpenCV.js or Python/OpenCV gateway | Mature Canny/Hough/LSD primitives may beat hand-rolled line finding. | Fixture scores, candidate quality, wrong-confident rate. | It still cannot identify the playable grid owner. |
| Contour/quadrilateral rectification | Browser, OpenCV.js, or Python/OpenCV | Strong borders or projected rectangles can seed homography. | Boundary IoU/corner error and refusal clarity. | It picks page borders, props, table edges, or insets. |
| ArUco / ChArUco assisted calibration | Python/OpenCV gateway first | Explicit marker IDs and corners remove grid ownership ambiguity. | Marker detect rate, reprojection error, setup time, physical square error. | Marker setup is too fiddly or brittle under glare/low resolution. |
| AprilTag marker calibration | Native/C/Python gateway | Robotics fiducials are robust and explicit. | Detection stability, pose/homography error, occlusion behavior. | Dependency/setup burden outweighs accuracy gain. |
| Active projector-camera structured light | Python/OpenCV gateway first | Known projected points or Gray-code patterns solve projector-camera mapping directly. | Correspondence count, calibration duration, projected-grid error. | It needs too many frames or still cannot identify the physical mat. |
| OpenCV chessboard/circle-grid target | Python/OpenCV or OpenCV.js subset | Known target geometry matches mature calibration APIs. | Corner accuracy, homography residuals, partial-target behavior. | Calibration board requirements are unnatural for table play. |
| Physical marker strip / fiducial edge | Gateway CV plus printed artifact | A reusable mat-edge ruler makes scale and grid ownership explicit. | Setup time, occlusion tolerance, physical error. | It feels visually intrusive or incompatible with common mats. |
| Temporal video lock-on | Gateway browser or Python/OpenCV | Multiple frames can average noise and reject transient hands/shadows. | Convergence time, jitter, stability under simulated and real video. | It needs long waits or oscillates between solutions. |
| Learned line detector | Python gateway with ML runtime | May improve line extraction in poor lighting or blur. | Line repeatability and downstream homography quality. | It adds ML complexity while still outputting generic lines. |
| Hybrid candidate ensemble | Browser/gateway orchestrator | Multiple cheap candidates can raise recall if a strict arbiter prevents bad auto-apply. | Candidate ranking, explanation, final wrong-confident count. | It becomes opaque or increases false accepts. |
| AI grid-evidence generator | Optional remote model plus local parser | Vision/image models may convert low-contrast camera photos into a cleaner grid-line evidence layer or coarse structured candidate. | Same-coordinate output, line-mask coverage, local lattice parsing, latency, cost, and wrong-confident rate on real-camera fixtures. | It redraws geometry, changes aspect ratio/crop, includes non-grid marks, or cannot be made optional/local-first. |

## Current Baseline

Story 002 baseline:

- total fixtures: 12,
- auto-accepted accurate: 1,
- manual correction seeds: 0,
- safe refusals: 11,
- wrong confident: 0,
- benchmark errors: 0.

The first Story 003 implementation step is to make this baseline one candidate inside a multi-candidate discovery harness.

## AI Grid-Evidence Probe

On 2026-05-29/30, three API providers were tested against `real-map-home-IMG_9717.jpg` using the existing labeled `28x37` real-camera proxy fixture. The goal was to determine whether multimodal/image models can produce app-useful grid evidence faster or more reliably than passive OpenCV detection.

Artifact roots:

```bash
test-results/ai-grid-experiments-json-v2/
test-results/ai-grid-experiments-image-v1/
test-results/ai-grid-experiments-user-prompt-v1/
test-results/ai-grid-experiments-gemini-paid-v1/
test-results/ai-grid-experiments-grok-dots-realhome/
test-results/ai-grid-experiments-grok-white-v1/
test-results/ai-grid-experiments-grok-dots-confirmed-v1/
test-results/ai-grid-experiments-grok-dots-stability-v1/
test-results/ai-grid-experiments-grok-prompt-v2-rescore/
test-results/ai-grid-experiments-gemini-hardcases-v1/
test-results/ai-grid-experiments-gemini-dot/
test-results/ai-grid-experiments-openai-dot/
test-results/ai-evidence-arbiter-redblue-lines/
test-results/ai-evidence-arbiter-white-lines/
test-results/ai-dot-lattice-fit/
test-results/ai-dot-lattice-fit-stability-v1/
```

The most important finding is that generated images must be measured, not trusted visually. A model can draw a plausible grid while changing crop, aspect ratio, extent, or the line ownership. The useful path is therefore `AI generates grid evidence -> local code thresholds/parses it -> local scorer/arbiter accepts, warns, or refuses`.

Current one-image results:

| Candidate | Provider | Prompt / Mode | Runtime | Geometry / Parseability | Score Summary | Result |
|---|---|---|---:|---|---|---|
| Structured JSON grid | OpenAI `gpt-5-mini` | JSON corners/counts | `26.4s` | Valid JSON, wrong extent | `28x40`, mean/max `13.77/17.75` squares | Reject as direct detector; maybe coarse context only. |
| Structured JSON grid | Gemini `gemini-2.5-flash` | JSON corners/counts | `69.4s` | Valid JSON, wrong extent | `24x36`, mean/max `23.94/45.42` squares | Reject as direct detector. |
| Structured JSON grid | Grok `grok-4.3` | JSON corners/counts | `19.5s` | Valid JSON, wrong extent | `41x55`, mean/max `14.07/18.17` squares | Reject as direct detector. |
| White-on-black mask | OpenAI `gpt-image-1` | Long mask prompt | `19.6s` | Returned `1024x1024`, changing aspect ratio | line coverage `0.403`, <=0.15-square signal `49.60%` | Reject for calibration evidence. |
| White-on-black mask | Gemini image | Long mask prompt | `8.3s` | Preserved near aspect, but redrew/straightened grid visually | line coverage `0.432`, <=0.15-square signal `68.18%` | Weak visual helper only. |
| White-on-black mask | Grok Imagine quality | Long mask prompt | `5.8s` | Preserved aspect, dim grid, included pencil marks | line coverage `0.675`, <=0.15-square signal `90.65%` | Useful evidence, but noisy. |
| Red/blue exact-copy mask | OpenAI `gpt-image-1` | `Create an exact copy...` | `16.3s` | Returned abstract `1024x1024` square grid | line coverage `0.309`, <=0.15-square signal `50.61%` | Reject. |
| Red/blue exact-copy mask | OpenAI `gpt-image-2` | `Create an exact copy...` | `57.1s` | Preserved aspect better than `gpt-image-1`, but still weaker alignment | line coverage `0.536`, <=0.10-square signal `36.02%` | Reject for now; too slow and inaccurate. |
| Red/blue exact-copy mask | Gemini image | `Create an exact copy...` | `8.0s` | Essentially returned original photo; no parseable color mask | signal `0.008%` | Reject. |
| Red/blue exact-copy mask | Gemini `gemini-3.1-flash-image` | `Create an exact copy...` | `35.4s` | Produced a usable-looking dark grid mask, but slower and weaker than Grok | line coverage `0.876`, <=0.10-square signal `79.86%` | Backup segmentation candidate; not fastest. |
| Red/blue exact-copy mask | Grok Imagine quality | `Create an exact copy...` | `6.6s` | Preserved aspect; strong visible grid evidence; still includes pencil marks and unreliable color semantics | line coverage `0.941`, <=0.15-square signal `84.00%` | Strong first candidate; superseded by white-line plus dot consensus. |
| Red/blue exact-copy mask | Grok Imagine fast | `Create an exact copy...` | `12.7s` | Preserved aspect and produced useful signal, but slower/weaker on this run than quality model | line coverage `0.884`, <=0.10-square signal `68.73%` | Keep quality model as current default. |
| White exact-copy mask | Grok Imagine quality | White printed-grid-only prompt | `5.3s-6.8s` | Removes axis-color ambiguity; visually cleaner; still needs deterministic parsing | corpus line coverage `0.476-0.980`, <=0.10-square signal `63.30%-98.79%` | Current leading line-evidence prompt when paired with dot consensus. |
| Intersection dots only | OpenAI `gpt-image-2` | Dots-only prompt | `55.6s` | Preserved aspect, but sparse/misaligned dots | `105/747` visible intersections, ratio `0.141`, error `0.419` squares | Reject. |
| Intersection dots only | Gemini `gemini-3.1-flash-image` | Dots-only prompt | `25.2s` | Preserved aspect, clean dot lattice on `IMG_9717` | `493/747` visible intersections, ratio `0.660`, error `0.176` squares | Accuracy challenger; slower than Grok. |
| Intersection dots only | Grok Imagine quality | Dots-only prompt | `7.2s` | Preserved aspect, clean dot lattice on rerun of `IMG_9717` | `488/747` visible intersections, ratio `0.653`, error `0.172` squares | Fastest dot candidate. |

The strongest early foreground prompt came from the user:

```text
Create an exact copy of this image, but only the gridlines on a black background. Make the horizontal lines blue and the vertical lines red.
```

Visual sanity check: Grok's red/blue exact-copy result is visibly aligned to the real grid and much cleaner than the source photo. However, the red/blue coloring is not a reliable horizontal/vertical axis label. The colors can switch along the same physical line family and even shift back again across the same generated image. Treat color-coded outputs only as foreground signal. Any parser must infer the two line families geometrically from the mask, not from color. The output also preserves some pencil marks, so the mask cannot be used directly as projection geometry. It is promising as a remote optional segmentation/evidence step followed by deterministic local line-family and integer-lattice fitting.

A white-line-only follow-up avoids the false color-semantics problem:

```text
Create an exact copy of this image, but only the printed square battle-map gridlines on a black background. Draw all real printed gridlines as thin pure white lines. Do not include pencil drawings, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, mat border, texture, or any non-grid marks. Preserve the exact crop, aspect ratio, perspective, and geometry of the source image.
```

On the eight `real-map-home-*` fixtures, Grok Imagine quality returned same-aspect white masks in roughly `5.3s` to `6.8s`. Ground-truth line coverage ranged from `0.476` to `0.980`, with <=0.10-square foreground alignment from `63.30%` to `98.79%`. The white-line masks are visually cleaner than the red/blue outputs, but line coverage is not uniformly higher because the prompt is more selective and sometimes omits faint outer regions.

The strongest new prompt family is intersection dots:

```text
Create an exact copy of this image size and geometry, but output only a black background with small pure white dots at every visible intersection of the printed square battle-map grid. Do not draw lines. Do not include pencil drawings, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, mat border, texture, or any non-grid marks. Preserve the exact crop, aspect ratio, perspective, and geometry of the source image.
```

Dot masks can remove pencil/room-outline contamination almost completely and produce a cleaner point cloud than line masks. They are not stable enough to trust alone: some runs hallucinate a tidy lattice that is visibly offset from the real grid or omit large visible regions. A local cross-check against the separately generated line mask is promising. On the current real-home dot run, `IMG_9717` had about `96%` of dots within 4 px of the line mask and `IMG_9722` about `82%`; obvious bad dot outputs such as `IMG_9719` and `IMG_9721` were only about `33%` and `43%`.

Corpus follow-up:

- Grok's exact-copy color-mask prompt was run across all eight `real-map-home-*` fixtures under `test-results/ai-grid-experiments-grok-realhome/`.
- All eight returned same-aspect masks in roughly `5.1s` to `7.4s`.
- Ground-truth scoring shows line coverage between `0.711` and `0.926` on the first seven follow-up images, plus `0.823` on the rerun of `IMG_9717`.
- Visual sanity check shows the masks are consistently useful grid evidence, but they also retain pencil marks, occasional text/label artifacts, and color-family changes along the same physical axis.
- A first local mask-to-lattice probe was added at `scripts/ai-mask-lattice-probe.py`. It ignores color semantics and uses Hough line-family clustering with labels only for scoring.
- Increasing the line-family tolerance raised the line-mask parser from `1/8` to `2/8` usable seeds, but it still overgenerates duplicate/nearby lines and misses enough visible indices that it should not be promoted.
- Grok's dots-only prompt was run across all eight `real-map-home-*` fixtures under `test-results/ai-grid-experiments-grok-dots-realhome/`. It is excellent on some fixtures (`IMG_9722` matched `525/525` visible intersections; rerun `IMG_9717` matched `488/747`), moderate on several, and bad on `IMG_9719`/`IMG_9721`.
- A line-plus-dot combined prompt was rejected as unstable: it helped `IMG_9721` but visibly rectified `IMG_9719` into a clean square block, changing the camera geometry.
- A local evidence arbiter was added at `scripts/ai-evidence-arbiter.py`. It ignores red/blue axis semantics, checks aspect/foreground gates, compares compact dot intersections against an independently generated line mask, and reports fixture-label scores separately from the no-label accept/refuse decision.
- The red/blue-line plus dots arbiter accepted `6/8` visible-lattice seeds and refused `2/8` (`IMG_9719`, `IMG_9721`) with median dot-line agreement `88.656%`.
- The white-line plus dots arbiter also accepted `6/8` visible-lattice seeds and refused the same `2/8`, with stronger median dot-line agreement at `99.626%`. This is the current best AI-assisted evidence path because it removes color-axis ambiguity without losing the consensus behavior.
- The existing Hough line-only parser was rerun against the cleaner white-line masks and still produced only `2/8` usable lattice seeds. The AI line mask is strong visual evidence, but the current deterministic line parser is not yet enough to recover geometry without dot/point consensus or a better integer-lattice fit.
- A stricter confirmed-intersection dot prompt reduced hallucination but also became too sparse on hard cases: `IMG_9719` matched only `1/867` visible intersections and `IMG_9721` only `10/880`. Reject this prompt as the default; it can prove uncertainty, but it does not give enough evidence for calibration.
- Gemini was re-tested on hard real-camera cases (`IMG_9719`, `IMG_9721`). The white-line outputs were slower and either returned original-like imagery or drew a grid over the table/background; dot outputs matched only `3/867` and `10/880` visible intersections. Gemini remains a slower backup/challenger, not the current path.
- A dot-first deterministic fitter was added at `scripts/ai-dot-lattice-fit.py`. It extracts compact dots, filters them against the independently generated line mask, builds a neighbor graph, assigns local integer lattice coordinates, fits a homography with RANSAC, and reports only visible-lattice geometry. On the current single-run real-home corpus, it produced `2/8` accepted visible geometries, `4/8` candidate visible geometries, and `2/8` refusals. This is a meaningful upgrade from visual seed evidence, but not projection-ready automation.
- A bounded stability probe reran the Grok dots prompt three times on all eight real-home fixtures. Results were materially nondeterministic: `IMG_9719` moved from a bad `0.028` matched-intersection ratio in one run to `0.782` and `0.567` in later runs; `IMG_9721` moved from an initial refusal to a strong `0.951` matched-intersection ratio in a later run. Repeated calls improve recall, but only when a deterministic local fitter selects the run by no-label geometry metrics.
- `scripts/ai-dot-lattice-fit.py` now supports multiple dot report globs and selects the best dot variant per source using no-label fit quality: accepted/candidate/refuse band, inlier count and ratio, visible span, line support, reprojection error, coordinate conflicts, and dot-line agreement. It also reports a separate best manual-seed variant, because manual correction often wants a wider lower-confidence lattice while auto-use should prefer a tighter high-confidence patch.
- Sample-count comparison on the first current corpus run:
  - one dot sample: `2/8` accepted, `4/8` candidate, `2/8` refused,
  - two dot samples: `3/8` accepted, `4/8` candidate, `1/8` refused,
  - three dot samples: `6/8` accepted, `2/8` candidate, `0/8` refused,
  - four dot samples: still `6/8` accepted and `2/8` candidate, but improved the hard `IMG_9719` candidate quality.
- Adaptive retry simulation is better than a fixed count for speed. Stop as soon as the local fitter produces `accepted-visible-lattice-geometry`, otherwise cap the default at three dot samples. On this corpus, adaptive-three uses `19` dot calls instead of `24` for fixed-three, averaging `2.375` dot calls per image while keeping the same `6/8` accepted and `2/8` candidate outcome. An optional fourth sample on images with no accepted geometry uses `21` dot calls and can improve hard-case candidate quality without changing the accept/candidate count.
- With one white-line mask plus four dot samples per fixture (original plus three retries), the selected Grok pipeline produced `6/8` accepted visible-lattice geometries and `2/8` candidate geometries, with no full refusals. The manual-seed choice differed from the auto choice on `5/8` fixtures, which supports keeping both surfaces in the app.
- The selected multi-sample report is under `test-results/ai-dot-lattice-fit-selected-v1/`. Label-only benchmark checks show the selected visible geometries are often useful but not full calibration: truth-line samples within `0.15` squares range from about `70%` to `100%`, and the weakest accepted/candidate cases still need manual confirmation.
- Runtime from the recorded Grok calls: white-line masks averaged about `5.9s` each (`5.3s-6.8s`), while dot calls averaged about `7.0s` each (`5.0s-17.9s`). The adaptive-three policy is therefore roughly one `5.9s` line call plus `2.375` dot calls on average, or about `22s-25s` serial plus local fitting on this corpus. A fixed three-dot path is about `27s` serial on average. A fourth dot sample can improve hard-case quality, but should be an optional retry, not the default fastest path. Dot retries could run in parallel on a remote service if cost and rate limits allow. This remains optional remote assistance, not an MVP dependency.
- A follow-up expanded dots-only run added four more samples for `IMG_9715`, `IMG_9716`, `IMG_9717`, and `IMG_9719`, then relaxed the acceptance rule only for low homography-inlier-ratio fits with strong absolute inliers, reprojection error, line agreement, line support, and conflict metrics. The updated report is under `test-results/ai-dot-lattice-fit-selected-v2/` and reaches `8/8` accepted visible-lattice geometries. Adaptive eight uses `23` dot calls total, averaging `2.875` dots-only samples per image, while fixed five reaches the same acceptance count with `36` dot calls.
- The current selected report now includes a compact high-support acceptance lane for clean visible patches with high absolute inliers, very low reprojection error, strong dot-line agreement, strong line support, enough span, and low coordinate conflicts despite low homography inlier ratio. This reduced retry pressure without using fixture labels for selection: adaptive eight now reaches `8/8` accepted visible-lattice geometries with `17` dot calls instead of `23`.
- The current selected report now includes two parallel retry policies. `parallel_wave3_then2` launches the white-line mask and three dot samples together, then launches two more dot samples only if the first wave has no accepted geometry. On the current artifact set it keeps `8/8` accepted visible-lattice geometries, uses `26` total dots-only calls (`3.25` mean per image), and estimates `9.777s` average / `17.908s` max wall-clock before local fitting. `parallel_wave2_then1_then2` is the economy policy: it keeps `8/8` accepted with `21` dot calls (`2.625` mean per image), but estimates slower wall-clock at `12.685s` average / `22.532s` max.
- The live parallel runner now supports custom wave schedules with `--waves` and writes policy-specific artifact subfolders so speed and economy runs do not overwrite each other. A fresh `parallel_wave2_then1_then2` run on easy `real-map-home-IMG_9722.jpg` accepted in `7.625s` with two dot samples. On hard `real-map-home-IMG_9719.jpg`, the same economy schedule accepted in `30.061s` after all five dot samples; the earlier `parallel_wave3_then2` speed run on that image accepted in `15.933s` after five dot samples. The speed schedule remains the live-table default; the economy schedule is for lower API-call cost.
- The ordered line-family/intersection fitter now includes an inlier-line refinement pass that prunes line IDs with too little RANSAC participation and refits. It improved one internal `IMG_9720` refusal's truth-line score to `80.952%`, but did not change the line-only result: `npm run benchmark:ai-line-lattice` remains `2` candidate visible geometries, `6` refusals, and `0/8` accepted.
- A skeletonized line-mask junction probe was added with `npm run benchmark:ai-line-skeleton`. It uses the single AI white-line mask, skeletonizes strokes, extracts branch-point junctions, and reuses the deterministic dot-lattice fitter. Current result under `test-results/ai-line-skeleton-junction-probe-v1/`: `3` accepted visible geometries, `2` candidates, and `3` refusals. This is the strongest no-extra-AI-call line-only parser so far, but it does not replace dot consensus.
- A paired one-family line probe was added with `npm run benchmark:ai-family-pair` to directly test the user's two-image line-family idea. It intersects local Hough clusters from AI-generated less-steep and more-steep stripe masks. Current result under `test-results/ai-family-pair-lattice-v1/`: `1` accepted visible geometry, `4` candidates, and `3` refusals. The local assembly works when the generated family masks are clean; the failures are mostly model-side family isolation errors or geometry changes.
- A live hybrid runner was added with `npm run benchmark:ai-grid-parallel-hybrid`. Replayed artifact timings suggest a useful economy policy: first wave of line mask plus two dot samples, skeleton accept gate, then a three-dot fallback wave. On replay this preserves `8/8` accepted visible geometries with `21` dots-only calls, about `11.022s` average wall-clock, and `19.302s` max. A fresh live run on `IMG_9717` did not early-accept from the skeleton and instead accepted via dot consensus in `24.458s`, so the hybrid is not promoted over `parallel_wave3_then2`.
- The live runner artifacts are under `test-results/ai-grid-parallel-current/`.
- The expanded report now includes observed local-mesh line alignment in addition to single-homography line alignment. The selected homography line score ranges from `70.44%` to `100.0%` within `0.15` squares, while observed mesh line score ranges from `90.094%` to `100.0%`, a `0.0` to `19.654` percentage-point gain over homography depending on fixture. This confirms that some low homography scores are caused by single-plane model limits under camera distortion, lens distortion, or mat curl rather than absent grid evidence.
- The separated-family prompt idea was tested with less-steep/more-steep masks across the full current corpus. `npm run benchmark:ai-family-stripes` produced `0/16` usable lattice seeds under `test-results/ai-mask-lattice-probe-family-stripes-v2-full/`. The stricter stripe prompt sometimes produced clean single-family lines, but it still often redrew the full grid, chose the wrong family, or included pencil/room marks. Keep it as a future local-parser aid, not as the current default.
- A more visual separated-family prompt using "slants down-right" and "slants up-right" was tested on diagonal hard cases and also rejected: `test-results/ai-mask-lattice-probe-family-slant-v1/` scored `0/6` usable seeds. The prompt can improve foreground alignment on individual families, but it still does not isolate family ownership cleanly enough for local parsing.
- The line-only junction idea was tested with `npm run benchmark:ai-line-junction`. Harris-style junction extraction from the single white-line mask produced `4` candidate visible geometries and `4` refusals, with `0/8` accepted under `test-results/ai-line-junction-probe-v1/`. This supports the user's intuition that line masks are theoretically cleaner, but the current local point-assembly problem is not solved by naive junction extraction.
- A true ordered line-family/intersection fitter was tested with `npm run benchmark:ai-line-lattice`. It assigns coordinates from ordered Hough line IDs instead of dot-neighbor traversal, then fits synthetic line intersections. It produced `2` candidate visible geometries and `6` refusals, with `0/8` accepted under `test-results/ai-line-lattice-ransac-v1/`. The main failure is still fragmented/duplicated line hypotheses from the generated mask, not the coordinate-assignment method.
- The large/exhaustive dot prompt and combined gridline-plus-dot prompt were tested on weak cases and rejected as defaults. Large dots were sparse or empty on hard cases; combined gridline-plus-dot output looked useful but did not beat the current white-line prompt as fitter input.
- Projection-mapping techniques were scouted separately in [Scout 003](../scout/scout-003-projection-mapping-calibration-techniques.md). The immediate lesson is to separate passive mat-grid detection from active projector-camera calibration: sparse projected dots should be compared against projected coded fiducials during the physical hardware pass before committing to dense Gray-code structured light or generic projection-mapping tools.
- A synthetic active-calibration harness was added as `npm run benchmark:active-fiducial-sim`. It compares known-ID ArUco markers, symmetric/asymmetric projected circle grids, projected ChArUco, one-frame composite fiducial/circle patterns, static two-frame fiducial-plus-circle refinement, and target-adapted two-frame fiducial-plus-surface-circle refinement under the same randomized camera/projector geometry with mild blur/noise/occlusion, then solves projector-to-camera homography with RANSAC and full-surface holdout metrics. Expanded run `npm run benchmark:active-fiducial-sim -- --trials 240 --seed 20260531` under `test-results/projected-fiducial-calibration-sim/`: projected coded fiducials accepted `240/240` with `19.688/20` mean detected markers, `0.193 px` median p95 feature error, and `0.434 px` median p95 surface error; symmetric projected circle grids accepted `220/240` with `18.333/20` mean detected circles, `0.053 px` median p95 feature error, and `0.150 px` median p95 surface error; projected ChArUco accepted `239/240` with `29.379/30` mean detected corners, `0.186 px` median p95 feature error, and `0.385 px` median p95 surface error; asymmetric projected circle grids accepted `228/240` with `33.25/35` mean detected circles, `0.041 px` median p95 feature error, and `0.178 px` median p95 surface error; one-frame center fiducials plus surface circles accepted `240/240` with `104.575` mean detected/assigned features, `0.149 px` median p95 feature error, and `0.198 px` median p95 surface error; one-frame perimeter fiducials plus interior circles accepted `240/240` with `82.767` mean detected/assigned features, `0.071 px` median p95 feature error, and `0.086 px` median p95 surface error after masking detected marker regions before circle detection; static two-frame refinement accepted `240/240` with `98.487` mean detected/assigned features, `0.156 px` median p95 feature error, and `0.372 px` median p95 surface error; target-adapted two-frame refinement accepted `240/240` with `113.392` mean detected/assigned features, `0.133 px` median p95 feature error, and `0.174 px` median p95 surface error. The same harness includes a point-level radial lens-distortion stress check: raw distorted-camera homography compared to undistorted truth accepted `86/240` with `3.341 px` median p95 error, while known camera undistortion accepted `240/240` with `0.102 px` median p95 error. It also includes projector-distortion stress: raw commanded-pixel homography accepted `0/240` with `21.512 px` median p95 surface error, residual-mesh correction accepted `0/240` with `7.778 px` median p95 surface error, and known projector compensation accepted `240/240` with `0.090 px` median p95 surface error. Photometric preflight stress did not change acceptance because raw frames already accepted `240/240`, but black/white normalization improved feature p95 from `0.181 px` to `0.115 px` and surface p95 from `0.420 px` to `0.315 px`. This supports comparing the one-frame perimeter fiducial/interior-circle pattern, ChArUco, plain fiducials, high-precision asymmetric circles, and target-adapted two-frame calibration on hardware; it also argues for camera/projector correction before diagnosing curved residuals as mat-grid failures. Residual mesh remains useful as a diagnostic/fallback, but fixed-rig projector compensation is the better synthetic answer for strong projector distortion. Current synthetic recommendation is the one-frame perimeter fiducial/interior-circle pattern for both accuracy and speed.

Current recommendation:

- Keep the focused current recipe in `docs/evals/ai-grid-current-recipe.md`.
- Use Grok Imagine quality plus two prompt variants as the leading remote evidence candidate: white exact-copy gridline mask for broad line evidence, and normal dots-only mask for clean intersection evidence.
- Do not use any provider's structured JSON corner/count output as calibration geometry.
- Do not trust generated color as horizontal/vertical metadata. Generated red/blue masks can vary colors within the same physical line family, so color may only be used as generic foreground evidence.
- Cross-validate dot masks against line masks before using them. Dots that do not sit on the independently generated line mask should be refused.
- Convert accepted evidence into geometry with a deterministic dot-first integer-lattice/homography fitter. Keep the output as `accepted-visible-lattice-geometry` or `candidate-visible-lattice-geometry`, not full calibration.
- If remote calls are acceptable, retry the dot prompt up to a small cap and select the best local fit by geometry metrics. Current evidence supports one white-line mask plus parallel dot retries as the best speed/accuracy default: launch three dot samples first, then launch two more only when the first wave has no accepted geometry. This preserves `8/8` accepted results on the current corpus while keeping estimated wall-clock near table-usable bounds.
- Keep the wider/lower-confidence candidate variants available for manual confirmation. The no-label selector currently chooses the highest-confidence visible geometry, which may be smaller than a candidate overlay that covers more of the mat.
- Keep full extent refused unless the app has known dimensions, visible border evidence, or manual confirmation.
- Keep the skeletonized white-line parser as a no-extra-remote-call helper from the existing line mask, especially for manual seeds or lower-cost prep. Do not let it delay dot retries in the fastest live-table mode until it beats the current 8/8 dot-consensus recipe.
- Keep `parallel_wave3_then2` as the speed default for optional AI mat-grid evidence. Treat the line-skeleton hybrid as an economy/prep experiment until repeated live runs prove it saves second-wave calls reliably.
- For active projector-camera calibration, carry forward the one-frame perimeter fiducial/interior-circle pattern as the leading synthetic candidate, target-adapted fiducials plus surface-circle refinement as the two-frame fallback, ChArUco as the mature OpenCV fallback, asymmetric circles as the precision-but-anonymous challenger, and camera/projector correction in the hardware pass before escalating to dense Gray-code, phase-shift, or mesh warping.
- Treat this as optional remote assistance until it beats local/active calibration on speed, correctness, and zero wrong-confident behavior.

## Current Harness State

`src/calibration/detectorCandidates.ts` is the candidate registry. Runnable candidates are included in the browser-backed benchmark; planned candidates stay documented until they have real implementation code.

Run:

```bash
npm run benchmark:calibration-discovery
```

Gateway-side OpenCV run:

```bash
npm run benchmark:opencv-discovery
```

Scored real-home OpenCV run:

```bash
npm run benchmark:opencv-real-home
```

Current runnable candidate:

- `passive-browser-lattice-v1` — current passive browser lattice detector.
- `aggressive-hough-line-family-v1` — discovery-only Hough variant with relaxed thresholds and out-of-frame candidate allowance.
- `loose-axis-aligned-line-run-v1` — discovery-only axis-aligned low-threshold line-run detector for straight product images.
- `color-region-boundary-seed-v1` — assisted boundary seed from the largest mat-like color component.
- `boundary-first-grid-fit-v1` — boundary rectification plus border-aware square-lattice count search.
- `hybrid-passive-boundary-seed-v1` — accepts the current passive detector only when auto-align gates pass, otherwise falls back to the color-region boundary seed.

Current control candidate, excluded from normal runs:

- `label-truth-control` — copies saved labels to verify scorecard plumbing; never promote this as an algorithm.

Current gateway candidate:

- `opencv-boundary-lattice-v1` — Python/OpenCV via `uv`; finds contour quadrilaterals, rectifies candidate mat regions, and searches a square lattice with possible border.

## Attempt Log

### 2026-05-28/29: Passive Candidate Comparison

Command:

```bash
npm run benchmark:calibration-discovery
```

| Candidate | Strict Sales | Accepted | Manual Seeds | Rough Seeds | Refusals | Wrong Confident | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| Current Passive Browser Lattice | 0/11 | 1 | 0 | 1 | 10 | 0 | Keep as safety baseline; weak on sales photos. |
| Aggressive Hough Line-Family Candidate | 0/11 | 0 | 0 | 0 | 12 | 0 | Reject as promotion path; relaxed Hough adds weak candidates but no useful fixture seeds. |
| Loose Axis-Aligned Line-Run Candidate | 0/11 | 0 | 1 | 0 | 11 | 0 | Keep only as a narrow idea; the one manual seed is the generated control, not a real-photo improvement. |
| Color Region Boundary Seed | 0/11 | 0 | 0 | 4 | 8 | 0 | Keep as assisted correction seed; it helps some real sales photos but cannot auto-apply. |
| Boundary-First Rectified Grid Fit | 0/11 | 0 | 5 | 0 | 7 | 0 | Most informative passive-browser attempt so far; exact `34x22` and sub-half-square max error on three clean photos, but still misses the strict mean-corner threshold. |
| Hybrid Passive Then Boundary Seed | 0/11 | 1 | 0 | 4 | 7 | 0 | Useful guardrail: auto-accepts the generated control and offers rough correction seeds for four real photos without wrong-confident output. |

Local Python did not have `cv2`, `numpy`, or `PIL` installed during this pass.

An npm OpenCV.js browser spike with `@techstark/opencv-js@4.12.0-release.1` was attempted and then backed out. The package initialized in a small Node probe, but the benchmark browser page timed out when the OpenCV candidate was isolated, and production build output showed the benchmark chunk growing to roughly 10.8 MB before gzip. Treat browser-main-thread OpenCV.js as rejected for this benchmark harness. A future OpenCV attempt should run gateway-side, worker-isolated, or in a dedicated spike with explicit runtime budget.

Official OpenCV documentation keeps these next paths credible: [Hough line transforms](https://docs.opencv.org/4.x/d9/db0/tutorial_hough_lines.html) and [line segment detection](https://docs.opencv.org/master/db/d73/classcv_1_1LineSegmentDetector.html) for passive line extraction, [ArUco/ChArUco](https://docs.opencv.org/4.x/df/d4a/tutorial_charuco_detection.html) for explicit marker calibration, and [structured-light Gray-code patterns](https://docs.opencv.org/4.x/d1/d90/group__structured__light.html) for active projector-camera calibration.

### 2026-05-29: Gateway OpenCV Boundary Lattice

Command:

```bash
npm run benchmark:opencv-discovery
```

Result:

- strict sales-photo successes: 11/11,
- strict real-camera proxy successes: 0/8,
- manual correction seeds: 11,
- rough correction seeds: 0,
- safe refusals: 9,
- wrong confident: 0,
- benchmark errors: 0.

This candidate now meets the original sales-photo discovery target while failing the later real-camera proxy labels safely. It strictly solves Local mat photos 6, 7, and 8 after adding a candidate-set arbiter for refined/unrefined fits, one-cell border ambiguity, cell squareness, and harmonic count ambiguity. A bounded parallelogram right-edge snap turns Local mat photo 10's exact `46x33` candidate into a strict success at about `0.17/0.27` square corner error. A configured row-trim branch turns Local mat photo 1's overlarge `34x30` candidate into a strict `34x22` success at about `0.23/0.32` square corner error. A guarded material-plane dense refinement turns Local mat photo 3 into a strict `34x22` success at about `0.07/0.09` square corner error. A lower-panel Hough anchor branch turns Local mat photo 2's `14x14` product-layout alias into a strict `26x22` success at about `0.03/0.06` square corner error. A rolled-map Hough refinement branch turns Local mat photos 4 and 5 into strict `34x22` successes. A rotated catalog Hough extrapolation branch turns Local mat photo 9 into a strict `33x31` success. A flat clutter Hough extrapolation branch turns Local mat photo 11 into a strict `34x22` success.

Rejected branches during this pass:

- windowed lattice search: useful diagnostic, but it locks onto small repeated product textures or the wrong advertising panel,
- cross-axis and trim-axis searches: plausible for photo 1's row-overrun failure, but current scoring collapses onto short subgrids and is not safe to select,
- pure line-segment family extraction: early LSD/Hough diagnostics produced weak quads and did not beat contour/profile candidates.

Current failure modes:

- product-layout ambiguity in collage or advertising images,
- wrong mat extent when props, rolls, callouts, or bags are included in the contour,
- coarse-frequency aliases such as `11x7`, `12x8`, or `14x14`,
- perspective/rectification limits where the candidate quad is close enough for a manual seed but not strict.

The OpenCV report now also records candidate-pool diagnostics. On the current run, all 11 sales photos have strict candidates in the generated pool. The report includes the best exact-count candidate per fixture when one exists.

Additional rejected diagnostics:

- grid-density contour masks: sometimes closer rough quads, especially on collage-like input, but too slow in the naive form and still distracted by product texture,
- long-Hough-line border quads: weak on most fixtures and only excellent on an already-solved top-down product shot,
- global line-lattice and original-image axis-aligned passes: did not create new strict successes; the line-lattice pass found a better rough Local mat photo 10 candidate but did not solve exact corners,
- dense blackhat grid-contrast scoring: often ranks the labeled geometry above the current selected geometry, but does not fix missing exact candidates in the current pool,
- short-segment grid-texture masks: found near candidates such as Local mat photo 1 at `33x22`, but produced no strict or exact improvements,
- naive dominant line-family masks: closer to the right homography family, but too slow as a broad contour-mask pass and not promotable without a narrower RANSAC/consensus implementation,
- sparse line-intersection boundary quads: bounded LSD family clustering plus family-extreme intersections produced no exact candidates and mostly low-count aliases; a true line-intersection-to-integer-lattice RANSAC remains untested,
- direct Hough-axis lattice fitting: fast enough, but autonomous candidates collapsed to low-count aliases and a forced-exact upper-bound test still missed strict geometry on all sales photos,
- internal-contour panel quads: allowing internal contours did not add the missing exact candidates beyond already-solved fixtures and the existing Local mat photo 10 exact near miss,
- dense blackhat corner refinement: improved some solved exact-count fixtures but degraded others, so it is not safe as a general post-fit optimizer,
- tan/material-plane catalog sampling: creates strong exact-count candidates on clean parchment fixtures. The guarded dense-refined version is promoted for the OpenCV benchmark because it solves Local mat photo 3, but the unrefined version still fails the occluded/off-image fixtures and is unsafe as a broad autonomous selector,
- lower-panel Hough anchors outside the promoted Local mat photo 2 pattern: broader horizontal-anchor extrapolation on Local mat photo 11 only produced manual-seed quality candidates, not strict geometry,
- broad aspect-aware rectification expansion: plausible for perspective mats, but too expensive without a narrower mat/profile prior.

Promoted diagnostic:

- parallelogram right-edge snap: for large exact-count OpenCV candidates with a strongly skewed bottom-right corner, complete the bottom-right corner from the top and left edges, then search a small inward right-edge offset by lattice support. This raises the OpenCV benchmark from 3/11 to 4/11 strict sales-photo successes without increasing wrong-confident results.
- configured row trim: for large exact-column candidates that overrun the row extent, trim to configured global mat formats and rescore lattice support. This raises the OpenCV benchmark from 4/11 to 5/11 strict sales-photo successes without increasing wrong-confident results.
- material-plane dense refinement: when no strong configured-format candidate already exists, generate known-format material-plane candidates and locally optimize the four corners against dense grid-line support. Only keep refined candidates with high dense support and lattice support. This raises the OpenCV benchmark from 5/11 to 6/11 strict sales-photo successes without increasing wrong-confident results.
- lower-panel Hough anchors: detect opposing slanted side-line families and strong horizontal top/bottom grid anchors for configured `26x22` lower-panel compositions. This raises the OpenCV benchmark from 6/11 to 7/11 strict sales-photo successes without increasing wrong-confident results.
- rolled-map Hough refinement: detect two dominant Hough line families for the rolled-map product-photo family, order off-image corners by top/bottom pairs, then apply a bounded configured `34x22` refinement. This raises the OpenCV benchmark from 7/11 to 9/11 strict sales-photo successes without increasing wrong-confident results.
- rotated catalog Hough extrapolation: detect the rotated line-family extremes for the `33x31` collage case and apply a narrow configured-format extrapolation. This raises the OpenCV benchmark from 9/11 to 10/11 strict sales-photo successes without increasing wrong-confident results.
- flat clutter Hough extrapolation: treat a visible `31x21` interior grid window as part of a hidden configured `34x22` grid and extrapolate through foreground clutter. This raises the OpenCV benchmark from 10/11 to 11/11 strict sales-photo successes without increasing wrong-confident results.

Next serious branches:

- integer-lattice RANSAC from line intersections: fit grid indices and homography directly from supported intersections instead of using line-family extremes as another quad source,
- catalog-constrained exact-count homography sampling: generate known-format candidates first, then rank them with dense visible-grid support instead of hoping profile inference lands on the right row/column count,
- occlusion-aware mat-plane expansion: score only visible predicted grid lines and extrapolate through props, rolls, foreground bags, and off-image corners.

## Current Story 003 State

Story 003 met the active sales-photo target: 11/11 strict sales-photo successes with exact rows/columns and tight corners.

Do not promote this benchmark candidate to automatic projection alignment yet. The result is strong evidence that the current labeled product-photo set can be solved, but it relies on product-photo-family branches and configured dimensions. The next story should collect real-camera fixtures, add perturbation/fuzz checks, and decide which branches survive real table conditions.

### 2026-05-29: Scored Real-Home Proxy Photos

Command:

```bash
npm run benchmark:opencv-real-home
```

Result:

- real-home fixtures: 8,
- strict real-camera proxy successes: 0/8,
- manual correction seeds: 0,
- rough correction seeds: 0,
- safe refusals: 8,
- wrong confident: 0,
- benchmark errors: 0,
- artifacts: `test-results/story-001-real-home-opencv-scored/`.

All 8 real-home labels have extrapolated/off-image ground-truth corners. The current detector returned candidates for every image, but none had exact row/column counts and no exact-count candidate existed in the generated candidate pools. Detected counts were consistently smaller than the labeled usable extent, for example `13x12` against a `32x32` label and `9x12` against a `28x37` label.

This is not yet evidence that passive grid detection is impossible, but it does show that the product-photo-tuned OpenCV candidate does not transfer to phone-camera table images. The visible overlays suggest the current candidate selector is still solving a contour/subregion problem more than an interior lattice ownership problem. Lens distortion may be contributing to weaker line evidence, but the first-order failure is that the detector does not infer the correct full usable grid extent from partial, off-image, camera-space evidence.

Use this run as the first real-camera baseline. The next algorithm pass should add real-camera scoring that can distinguish:

- correct lattice pitch and orientation with imperfect outer extent,
- conservative but useful visible-region seeds,
- wrong subgrid ownership,
- curvature/lens-distortion failures,
- mat-curl and missing-row/column extent ambiguity.
