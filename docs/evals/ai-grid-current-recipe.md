# Current AI Grid Evidence Recipe

This is the current best optional remote-assistance path for extracting grid evidence from real-camera mat photos. It is a research/eval recipe, not an MVP dependency and not a replacement for local calibration.

## Current Decision

Use Grok image generation as a grid-evidence generator, then let local deterministic code decide whether the evidence is usable.

The current leading approach is layered, not a single detector:

1. Generate one white gridline mask with `white-grid-exact-copy-no-marks-v1`.
2. Parse that line mask two ways locally:
   - as independent line evidence for dot validation,
   - as an observed grid graph with `scripts/ai-line-graph-lattice.py`.
3. Generate dots-only intersection masks with `white-intersection-dots-no-lines-v1` when a homography/manual-seed candidate is needed.
4. Retry the dots-only prompt adaptively because model outputs are nondeterministic.
5. Fit visible lattice geometry locally with `scripts/ai-dot-lattice-fit.py`.
6. Evaluate full-span single-homography line alignment, homography alignment over observed mesh edges, and observed local-mesh alignment. The mesh metric connects adjacent detected intersections directly; the same-edge homography baseline separates true local-mesh benefit from an easier sampling domain.
7. Export a conservative auto-projection selection, a separate manual-correction seed, and an observed inlier mesh for diagnostics/future local warp work.
8. Return only `accepted-visible-lattice-geometry`, `candidate-visible-lattice-geometry`, or `refuse` as the dot-consensus geometry decision, plus separate projection-readiness states. The line-graph path returns observed-grid graph decisions and should be treated as local mesh evidence, not a full-span homography.

The output is visible-lattice geometry only. Full mat extent still needs known dimensions, visible border evidence, or manual confirmation. The manual-correction seed is intentionally allowed to prefer a wider coherent candidate than the auto-projection selection; candidate seeds still require human confirmation before projection.

The current reports also include projection-model comparisons and projection-readiness splits. This does not change the geometry decision or auto-selection. Its purpose is to avoid overclaiming: full-span homography, observed-edge homography, observed inlier mesh, benchmark-backed readiness, and runtime-safe no-label readiness are reported separately so mesh-warp ideas are judged only against the same observed-edge domain, and an accepted visible lattice does not automatically mean full-span projection is safe.

## Projection Seed Modes

The labeler exposes the current AI result as multiple seed modes because "the lattice is correct" and "the projected extent is safe" are now separate questions.

| Mode | Purpose | Runtime Safety |
|---|---|---|
| Supported visible patch | Tight rectangle around observed inlier mesh cells, with the labeler trimming obvious source-image foreground/non-mat cells. This is the safest seed and explains why the current overlay can look too small. | Best candidate for autonomous observed-region projection, but still requires readiness gates. |
| Selected dot extent | Uses the selected dot lattice coordinate bounds, including fitted lines without full observed-cell support. The fitter now exports exact coordinate bounds so this is no longer a centered estimate around observed support. | Candidate/manual extent check. Useful when the supported patch is too conservative, but it may extrapolate into occluders or foreground. |
| Wider manual span | Uses the lower-confidence manual-seed span as a diagnostic correction start. | Human review only. It may use a different dot variant and must not auto-project. |
| Label-sized diagnostic | Uses saved fixture row/column counts to visualize whether the lattice would align at the human-labelled extent. | Eval-only. It uses ground truth and is unavailable at runtime. |

The labeler can also draw observed AI support cells separately from the rectangular virtual grid. This overlay is off by default because it is diagnostic, not the projection seed itself. It is important for cases like `real-map-home-IMG_9719.jpg`: the rectangular grid can extend into a foreground area with no visible printed grid, while the support-cell overlay shows where the AI evidence actually exists.

Fresh labeler-seed mode sweep on the eight `real-map-home-*` fixtures:

| Source | Supported Patch | Selected Fit Span | Wider Manual Span | Label-Sized Diagnostic |
|---|---:|---:|---:|---:|
| `IMG_9715` | `25x13` | `27x23` | `31x29` | `32x41` |
| `IMG_9716` | `25x20` | `33x27` | `33x27` | `32x32` |
| `IMG_9717` | `23x22` | `33x22` | `33x22` | `28x37` |
| `IMG_9718` | `16x16` | `25x23` | `28x30` | `28x33` |
| `IMG_9719` | `11x18` | `17x22` | `28x28` | `29x33` |
| `IMG_9720` | `15x23` | `21x24` | `25x24` | `32x39` |
| `IMG_9721` | `25x23` | `27x29` | `27x29` | `29x34` |
| `IMG_9722` | `28x23` | `28x23` | `28x23` | `22x25` |

Interpretation: the AI-assisted pipeline is generally finding the right grid family, but the autonomous extent selector is still conservative or uneven. The next product decision should not be "does AI find the grid?" in isolation. It should be "which seed mode is safe enough to offer automatically, and which modes should remain manual correction starts?"

After adding exact coordinate bounds to the fitter, the current summary is regenerated from the live parallel artifacts under `test-results/ai-grid-parallel-current/`. The labeler uses these summary artifacts first, falling back to the latest live parallel report only when a source is absent from the summary.

The current summary is a best-available artifact pool, not a clean live retry-speed replay. It now includes expanded wave-eight hard-case runs for `IMG_9716` and `IMG_9717`, so it is appropriate for labeler seeding and selector evaluation. Do not use its mixed-artifact retry-policy rows as final live latency evidence; live speed claims should come from individual `parallel-report.json` runs with one source, one line mask, and one dot schedule.

Line-mask-only parsing was rechecked against the same current line artifacts:

| Probe | Current Result | Interpretation |
|---|---:|---|
| Ordered line-family lattice | `3` candidate, `5` refused | Still weaker than dot consensus; line clusters fragment and alias. |
| Raw junction extraction | `2` accepted, `1` candidate, `5` refused | Too unstable and several accepted scores are poor. |
| Skeleton junction extraction | `4` accepted, `3` candidate, `1` refused | Best no-extra-dot-call challenger, but accepted cases include weak label scores around `77-84%`, so it stays diagnostic/manual-seed only. |
| Observed grid graph | `8` accepted observed-grid graphs | Promising one-line-mask path for local mesh/warp evidence: mean observed-mesh alignment `97.009%`, min `89.482%` on the eight real-home fixtures. It is not a full-span homography or full-mat extent proof. |

Conclusion: keep the Grok line mask as an independent dot validator, and keep the observed-grid graph as a serious local-mesh challenger. Do not replace dot consensus for full-span homography/manual seed yet; the graph path solves a different problem and is most relevant to observed-region projection or future mesh-warp projection.

Prompt-ablation note from 2026-05-31: shorter prompts are not automatically better, and longer prompts are not automatically worse. A concise line prompt based on "draw white gridlines overtop the actual printed gridlines" was tested on `IMG_9715`, `IMG_9717`, and `IMG_9719`; it downgraded the first two to candidate/manual-review and only kept `IMG_9719` accepted. A second simple prompt close to the user's suggested wording (`white-grid-simple-only-v4`) was also tested on the same hard cases through the line-graph parser; it scored selected-line alignment `66.319%`, `99.951%`, and `92.536%`, below the current default's `95.964%`, `100.0%`, and `95.413%` on those sources. Stricter "printed-only" and freehand-emphasis prompts sometimes made the visible line mask cleaner, but they also changed real grid evidence enough to hurt the deterministic fitter. The same original white-grid prompt regenerated as a fresh line mask was the best prompt branch tested, but even that is variable enough that line-mask retries should be treated as an evidence source, not a prompt replacement. A concise dots-only prompt was worse than the current dots prompt, and a line-mask-to-dots prompt created many spurious dots.

Original-photo line-contrast scoring was also tested as a local no-label selector proxy. It is rejected for now: shadows, glare, and hand-drawn marks can produce stronger dark-line contrast than the actual grid, so it did not reliably separate good graph/dot variants from bad broad variants.

Benchmark projection-readiness scoring is eval evidence because it uses labeled full-span and observed-edge scores. The scorer now also emits `noLabelProjectionReadiness`, which uses only fit metrics, observed inlier-mesh support, early-return safety, and accepted-variant ambiguity flags. Treat the no-label field as the runtime safety gate; treat benchmark readiness as validation evidence for whether the conservative gate is too strict or too loose.

Benchmark projection-readiness modes:

- `full-span-homography`: candidate for automatic full-span projection.
- `full-span-homography-with-manual-extent-check`: geometry is plausible, but extent should be confirmed before projection.
- `observed-edge-homography-only`: supported observed grid edges look good, but unsupported full-span extrapolation is not trusted.
- `manual-confirmation-required`: do not project automatically.

No-label projection-readiness modes:

- `no-label-full-span-candidate`: runtime metrics are strong enough for full-span auto-project candidacy.
- `no-label-manual-extent-check`: visible lattice geometry is usable, but full-span extent should be confirmed before projection.
- `no-label-observed-region-candidate`: observed-region evidence exists, but no-label support is too sparse or low-ratio to extrapolate the whole fitted span.
- `no-label-manual-confirmation-required`: do not project automatically.

## Provider Notes

| Provider | Current Use | Reason |
|---|---|---|
| Grok Imagine quality | Leading candidate | Fastest useful line and dot evidence on the current real-home photos. |
| Gemini image | Backup/challenger | Sometimes useful, but slower and weaker on hard cases in current tests. |
| OpenAI image | Rejected for now | Too slow and less accurate on current line/dot prompts. |
| Structured JSON from all providers | Rejected for geometry | Returned valid-looking but wrong corners/counts. |

## Color Warning

Do not infer horizontal or vertical axes from generated red/blue masks.

The prompt:

```text
Create an exact copy of this image, but only the gridlines on a black background. Make the horizontal lines blue and the vertical lines red.
```

can produce strong foreground grid evidence, but the colors are not stable metadata. A single physical line family can switch from red to blue and back across the same generated image. Treat these outputs as foreground segmentation only, and infer line families geometrically if they are used at all.

The current recipe prefers white gridline masks plus white intersection dots to avoid the false color-axis contract.

## Prompts

Line evidence:

```text
Create an exact copy of this image, but only the printed square battle-map gridlines on a black background. Draw all real printed gridlines as thin pure white lines. Do not include pencil drawings, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, mat border, texture, or any non-grid marks. Preserve the exact crop, aspect ratio, perspective, and geometry of the source image.
```

Intersection evidence:

```text
Create an exact copy of this image size and geometry, but output only a black background with small pure white dots at every visible intersection of the printed square battle-map grid. Do not draw lines. Do not include pencil drawings, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, mat border, texture, or any non-grid marks. Preserve the exact crop, aspect ratio, perspective, and geometry of the source image.
```

The stricter confirmed-intersections prompt was too sparse on hard cases and is not the default.

## Current Score

Current selected report:

```bash
test-results/ai-dot-lattice-fit-risk-aware-summary-v1/report.md
```

Summary on the eight `real-map-home-*` proxy photos:

Current guarded risk-aware dot-consensus summary:

- Geometry decisions: `8/8` accepted visible-lattice geometry.
- Full-span homography line alignment: mean `90.532%`, min `66.443%`.
- Observed-edge homography line alignment: mean `97.672%`, min `87.224%`.
- Observed local-mesh line alignment: mean `96.829%`, min `84.122%`.
- Projection readiness: `4` full-span homography, `1` full-span homography with manual extent check, `2` observed-edge-only, `1` manual confirmation required.
- No-label readiness: `1` full-span candidate, `5` manual extent check, `1` observed-region candidate, `1` manual confirmation required.
- Benchmark oracle diagnostics still show material selector misses on `IMG_9715` and `IMG_9721`; these are evidence for the observed-grid graph branch and better no-label selectors, not permission to use labels at runtime.

Current line-graph observed-mesh summary:

- Command: `npm run benchmark:ai-line-graph`.
- Geometry decisions: `6/8` accepted observed-grid graphs, `2/8` candidate observed-grid graphs.
- Observed local-mesh alignment: mean `97.958%`, min `89.073%`.
- Report-only selected line alignment after the conservative grown-extent gate: mean `98.820%`, min `95.413%`.
- The grown-extent gate trusted exactly one case, `IMG_9715`, where a modest one-axis expansion of the local graph improved the hard under-extent score from `89.073%` to `95.964%`.
- This uses one line-mask image and local graph parsing only. It does not produce full-span homography readiness or full-mat extent by itself.
- The current parser uses four-way skeleton junctions and penalizes skinny graph components. This improved the observed-mesh floor, but it still selects only observed local graph patches rather than a guaranteed full-mat rectangle.
- The grown-extent gate is report-only: it requires high generated-line support, modest expansion, and mostly one-axis growth, but it still needs a larger real-photo corpus before it should affect runtime projection.
- Concise prompt work did not beat the default prompt. `white-grid-solid-only-v6` and pink-overlay variants can look good visually, but repeated checks showed they can regularize row counts, include non-grid marks, or become harder to parse. The default `white-grid-exact-copy-no-marks-v1` remains the current line-mask prompt.
- Two-step AI conversion from generated line masks to intersection dots is rejected for now. It creates plausible dots, but the model regularizes the grid and the deterministic fitter scores worse than the original-photo dot consensus.
- Provider comparison on the hard `IMG_9715` case did not justify switching providers: Grok remained the only provider producing useful line-mask artifacts in this harness; OpenAI and Gemini outputs changed crop/geometry or failed to isolate the grid.

Current report-only hybrid summary:

- Command: `npm run benchmark:ai-grid-hybrid-summary`.
- Branches: `6` line-graph selections, `2` dot-consensus selections.
- Selected-line alignment: mean `99.393%`, min `95.964%`.
- The hybrid uses line-graph selected-line geometry by default, switches to dot consensus for no-label full-span candidates, and switches to dot consensus when the line graph is only a candidate and the dot fit has strong no-label support.
- On the current corpus this means line graph owns `IMG_9715`, including the trusted grown extent, while dot consensus owns the no-label full-span `IMG_9716` and high-support manual-extent `IMG_9719`.
- This is still report-only. The selector combines two candidate families with different failure modes and needs a larger real-photo corpus before runtime promotion.

Current line-first speed model:

- Command: `npm run benchmark:ai-grid-hybrid-summary`.
- Branches: `7` line-graph-first-pass selections, `1` dot-consensus fallback.
- Selected-line alignment: mean `99.393%`, min `95.964%`, matching the accuracy-oriented hybrid on the current corpus.
- The model runs one line-mask call for each source, then spends dot-consensus calls only when the line graph is neither accepted nor trusted by the grown-extent gate.
- On the current corpus only `IMG_9719` triggers dot fallback. `IMG_9716` no longer needs dot consensus in this speed model because the line graph already scores `100.0%` there; the accuracy-oriented hybrid chooses dots for it only because dots provide no-label full-span readiness.
- This is a report-only cost/latency model, not a live runner yet. It needs fresh live measurements and a larger real-photo corpus before it can replace the current parallel dot policy.

Live line-first measurements:

- Command: `npm run benchmark:ai-grid-line-first-current`.
- Single-line `IMG_9716` stopped without dot fallback in `8.744s`, scoring `100.0%` selected-line and `100.0%` mesh alignment.
- Single-line `IMG_9715` did not reproduce the report-only trusted-grown line result; it fell back to four dots and accepted in `16.255s`, scoring `100.0%` line and `100.0%` mesh alignment.
- Single-line `IMG_9719` fell back to four dots and accepted in `19.893s`, scoring `100.0%` line and `100.0%` mesh alignment without the safe-required gate. With `--require-safe-accept`, the same shape took `24.118s` and downgraded a label-good result (`95.224%` line, `99.688%` mesh) to candidate because coordinate conflicts failed the no-label safety floor.
- Three parallel line samples are not a speed win in the current Grok API path. `IMG_9715` avoided dot fallback but took `39.735s` total, with `32.039s` in line generation. `IMG_9719` still needed dot fallback and took `62.565s`.
- Conclusion: keep the live line-first runner as a diagnostic. Do not promote serial line-first as the table-speed default unless repeated live runs show line-only stop rates high enough to offset the slow fallback path. The next speed candidate should probably combine line-graph gating with speculative parallel dots rather than waiting to start dots until after the line result.

| Policy | Dot Calls | Result |
|---|---:|---|
| fixed one sample | 8 | 1 accepted, 5 candidate, 2 refused |
| fixed two samples | 16 | 4 accepted, 4 candidate, 0 refused |
| fixed three samples | 24 | 8 accepted, 0 candidate, 0 refused |
| fixed four samples | 32 | 8 accepted, 0 candidate, 0 refused |
| fixed five samples | 40 | 8 accepted, 0 candidate, 0 refused |
| adaptive three samples | 19 | 8 accepted, 0 candidate, 0 refused |
| adaptive three plus candidate fourth | 19 | 8 accepted, 0 candidate, 0 refused |
| adaptive eight samples | 19 | 8 accepted, 0 candidate, 0 refused |
| parallel wave three then two | 24 | 8 accepted, 0 candidate, 0 refused; replay wall avg `9.263s`, max `11.726s` |
| safe streaming wave three then two | 32 | 8 accepted, 0 candidate, 0 refused; replay wall avg `12.858s`, max `20.088s` |
| parallel wave two then one then two | 20 | 8 accepted, 0 candidate, 0 refused; replay wall avg `13.324s`, max `21.014s` |
| guarded risk-aware selection | same launched/completed dots as chosen retry policy | 8 accepted, 0 candidate, 0 refused; accuracy challenger only |

Use adaptive three as the current highest-recall serial replay default on the current mixed artifact pool: stop once local fitting produces accepted visible geometry, otherwise continue up to three dots-only samples. It reaches 8/8 accepted with 19 total dots-only calls in the current artifact pool. Treat this as replay evidence, not live speed proof.

For wall-clock speed with balanced API cost, the current dot-consensus default remains `parallel_wave3_then2`: issue the white-line mask plus three dots-only samples in parallel, score as soon as the first wave returns, and issue two more dots-only samples only when the first wave has no accepted geometry. On the current artifact set it keeps `8/8` accepted results, uses `24` total dots-only calls (`3.0` mean per image), and estimates `9.263s` average / `11.726s` max wall-clock before local fitting.

The best balanced replay speed-mode is `stream_wave3_then2`: keep the same wave sizes and launched-dot budget as `parallel_wave3_then2`, but score completed dot reports as they arrive after the line mask is available and proceed at the first accepted visible geometry. On the current artifact set it keeps `8/8` accepted results, still launches `26` total dots-only calls, needs `19` completed dot reports before first acceptance, and estimates `7.782s` average / `15.096s` max wall-clock. However, raw first-accepted streaming is not always early-return safe: `6/8` first accepted choices pass the conservative safety floor. The safer variant, `safe_stream_wave3_then2`, keeps `8/8` accepted and `8/8` early-return-safe choices, using `28` launched dots, `21` completed dots before safe accept, and `8.448s` average / `15.096s` max estimated wall-clock. Treat the safe variant as the candidate; keep raw streaming as a diagnostic.

For maximum replay speed, `parallel_fixed5` keeps `8/8` accepted results and estimates `9.101s` average / `17.908s` max wall-clock, but uses `36` dots-only calls (`4.5` mean per image). A fresh live check on `IMG_9719` did not reproduce auto acceptance with five fixed samples, so do not promote this to the live default without more repeated live runs.

The strongest replayed speed candidate is now `safe_stream_fixed5`: launch the line mask plus up to five dot samples, score dots as they complete, and proceed at the first early-return-safe accepted geometry while the already-launched calls may finish in the background. On the current artifact set it keeps `8/8` accepted and `8/8` early-return-safe results, launches the same `36` dots-only calls as `parallel_fixed5`, needs `17` completed dot samples before safe acceptance, and estimates `6.563s` average / `10.633s` max wall-clock. Raw `stream_fixed5` is faster in replay (`5.993s` average / `6.789s` max) but only `6/8` first accepted choices pass the safety floor after the mid-large low-ratio gate, so do not use raw first-accept as a live return condition.

Fresh `parallel_wave5 --measure-early-accept` checks support the shape but not the full replay speed claim: `IMG_9719` accepted at `8.531s` after 2 completed dots and drained at `10.936s`; `IMG_9722` accepted at `8.903s` after 1 completed dot and drained at `11.892s`. This is useful table-speed upside, but the measured live savings are about 2-3 seconds on those runs, not a guaranteed sub-7-second path.

For lower API cost, `parallel_wave2_then1_then2` keeps `8/8` accepted results with `21` total dots-only calls (`2.625` mean per image), but estimates slower wall-clock at `12.685s` average / `22.532s` max because medium-hard images wait for a third sequential wave. Treat this as an economy/prep mode, not the fastest live-table default.

An experimental hybrid economy policy now exists as `npm run benchmark:ai-grid-parallel-hybrid`. It launches the white-line mask plus two dot samples, lets the skeletonized line-mask parser accept only if dot consensus has not accepted, and otherwise launches three more dot samples. On the current replayed artifact set this preserves `8/8` accepted results, uses the same `21` dots-only calls as `parallel_wave2_then1_then2`, and improves the estimated replay wall-clock to about `11.022s` average / `19.302s` max. This is a replay estimate, not the default live policy.

A live parallel runner now measures the retry policies with fresh API calls:

```bash
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9719.jpg
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9719.jpg --waves 5
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9719.jpg --waves 5 --measure-early-accept
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9719.jpg --waves 3,2 --measure-early-accept
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9722.jpg --waves 5 --measure-early-accept
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9722.jpg --waves 3,2 --measure-early-accept
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9722.jpg
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9722.jpg --waves 2,1,2
npm run benchmark:ai-grid-parallel-hybrid -- --source-id real-map-home-IMG_9717.jpg
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9715.jpg --waves 3,2 --measure-early-accept --run-id post-gate-repeat-001
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9715.jpg --waves 3,2 --measure-early-accept --require-safe-accept --run-id safe-stop-repeat-001
```

Use `--run-id` when repeating the same source and policy; otherwise the policy folder is intentionally reused for the latest live measurement.

Observed runs:

| Source | Policy | First Wave | Final | Dot Samples | Total Wall | Homography <=.15 | Mesh <=.15 |
|---|---|---|---|---:|---:|---:|---:|
| `real-map-home-IMG_9719.jpg` | `parallel_wave3_then2` | candidate in `6.798s` | accepted | 5 | `15.933s` | 85.172% | 100.0% |
| `real-map-home-IMG_9719.jpg` | `parallel_wave3_then2` | accepted in `11.149s` | accepted | 3 | `12.794s` | 100.0% | 100.0% |
| `real-map-home-IMG_9719.jpg` | `parallel_wave3_then2` + cached early measurement | candidate in `8.740s` | candidate | 5 | `17.796s` | 72.845% | 94.551% |
| `real-map-home-IMG_9719.jpg` | `parallel_wave5` | candidate in `9.914s` | candidate | 5 | `14.072s` | 86.653% | 99.322% |
| `real-map-home-IMG_9719.jpg` | `parallel_wave5` + cached early measurement | accepted at `8.531s` after 2 completed dots | accepted | 5 | `10.936s` | 95.353% | 94.967% |
| `real-map-home-IMG_9719.jpg` | `parallel_wave2_then1_then2` | candidate in `11.758s` | accepted | 5 | `30.061s` | 94.048% | 97.699% |
| `real-map-home-IMG_9722.jpg` | `parallel_wave5` + cached early measurement | accepted at `8.903s` after 1 completed dot | accepted | 5 | `11.892s` | 97.145% | 98.415% |
| `real-map-home-IMG_9722.jpg` | `parallel_wave3_then2` + cached early measurement | accepted in `9.964s`; first accepted geometry was visible at `9.207s` after 2 completed dots | accepted | 3 | `9.964s` | 99.843% | 99.937% |
| `real-map-home-IMG_9722.jpg` | `parallel_wave3_then2` + safe early measurement | first accepted at `8.106s` after 1 dot; first early-return-safe at `8.804s` after 2 dots | accepted | 3 | `10.137s` | 100.0% | 100.0% |
| `real-map-home-IMG_9722.jpg` | `parallel_wave2_then1_then2` | accepted in `6.056s` | accepted | 2 | `7.625s` | 100.0% | 100.0% |
| `real-map-home-IMG_9717.jpg` | `parallel_wave2_then3_line_skeleton` | candidate in `9.634s` | accepted | 5 | `24.458s` | 72.034% | 78.031% |
| `real-map-home-IMG_9715.jpg` | `parallel_wave3_then2` + cached early measurement, before borderline support/conflict gate | accepted at `7.485s` after 2 completed dots | accepted | 3 | `8.267s` | 62.942% | 61.024% |
| `real-map-home-IMG_9715.jpg` | same artifacts rescored after borderline support/conflict gate | no unsafe early accept; selected first-wave high-support fit | accepted | 3 | `8.267s` | 100.0% | 100.0% |
| `real-map-home-IMG_9715.jpg` | fresh `parallel_wave3_then2` after borderline support/conflict gate | accepted at first-wave drain after 3 completed dots | accepted | 3 | `9.691s` | 82.008% | 94.558% |
| `real-map-home-IMG_9715.jpg` | fresh `parallel_wave5` after inlier-ratio/mesh-density safety gate | first early-return-safe at `11.816s` after 3 completed dots | accepted | 5 | `13.013s` | 97.764% | 99.326% |
| `real-map-home-IMG_9715.jpg` | fresh `parallel_wave5` + guarded mesh-density selection + safe accept + summary-only | first accepted and safe at `8.696s` after 4 completed dots | accepted | 5 | `10.520s` | 72.642% | 86.708% |
| `real-map-home-IMG_9715.jpg` | fresh `parallel_wave5` + guarded risk-aware selection + safe accept + summary-only | first early-return-safe at `6.984s` after 4 completed dots | accepted | 5 | `7.480s` | 99.167% | 100.0% |
| `real-map-home-IMG_9717.jpg` | fresh `parallel_wave8` + guarded risk-aware selection + safe accept + high-precision compact challenger | first safe accepted at `8.283s` after 6 completed dots | accepted | 8 | `8.383s` | 94.707% | 100.0% |
| `real-map-home-IMG_9717.jpg` | fresh `parallel_wave6` + guarded risk-aware selection + safe accept + high-precision compact challenger | first safe accepted at `6.979s` after 4 completed dots | accepted | 6 | `7.881s` | 82.267% | 95.74% |
| `real-map-home-IMG_9717.jpg` | fresh `parallel_wave4_then2` + guarded risk-aware selection + safe accept + high-precision compact challenger | first safe accepted at `8.251s` after 3 completed dots | accepted | 4 | `8.320s` | 87.888% | 98.719% |
| `real-map-home-IMG_9717.jpg` | repeat `parallel_wave4_then2` + guarded risk-aware selection + safe accept + high-precision compact challenger | first safe accepted at `6.772s` after 3 completed dots | accepted | 4 | `7.562s` | 92.005% | 100.0% |
| `real-map-home-IMG_9717.jpg` | second repeat `parallel_wave4_then2` + guarded risk-aware selection + safe accept + high-precision compact challenger | first safe accepted at `6.482s` after 1 completed dot | accepted | 4 | `7.218s` | 88.313% | 100.0% |
| `real-map-home-IMG_9715.jpg` | fresh `parallel_wave4_then2` + guarded risk-aware selection + safe accept, before large-span safety gate | first safe accepted at `9.116s` after 3 completed dots | accepted | 4 | `9.343s` | 69.345% | 81.95% |
| `real-map-home-IMG_9715.jpg` | fresh `parallel_wave4_then2` + guarded risk-aware selection + safe accept, after large-span safety gate | no safe accepted geometry before drain; current safe-required selector downgrades this to candidate | candidate | 6 | `14.693s` | 68.899% | 89.814% |
| `real-map-home-IMG_9717.jpg` | fresh `parallel_wave5` + guarded risk-aware selection + safe accept + summary-only, before mid-large safety gate | current safe-required selector downgrades this to candidate | candidate | 5 | `9.118s` | 77.466% | 93.801% |
| `real-map-home-IMG_9717.jpg` | fresh `parallel_wave5_then3` + guarded risk-aware selection + safe accept + summary-only | first-wave safe accepted geometry at `10.552s` after 4 completed dots; projection confidence is observed-edge-only | accepted | 5 | `11.791s` | 84.593% | 99.596% |

Artifacts are under `test-results/ai-grid-parallel-current/`; new live runs write policy-specific subfolders such as `real-map-home-IMG_9722/parallel_wave2_then1_then2/` so speed and economy evidence do not overwrite each other. These runs confirm the policies work operationally, not only as replayed timing estimates. The hard-case economy run shows the tradeoff clearly: it saves calls in replayed policy accounting, but can be much slower than the speed policy when it needs all three waves.

The first live hybrid check did not reproduce the replayed line-skeleton early accept on `IMG_9717`: the fresh line mask only produced a candidate skeleton geometry, so the runner correctly fell back to dot consensus and took `24.458s`. Keep the hybrid command as an experimental economy/prep mode until repeated live runs show that the skeleton gate avoids enough second waves to justify the extra branch.

A fresh `IMG_9717` wave-eight run after the high-precision compact challenger is more encouraging: the run accepted in `8.383s`, with the first safe accepted geometry at `8.283s` after six completed dot reports, scoring `94.707%` full-span homography-line and `100.0%` observed mesh alignment. The first raw accepted geometry in that run was a broader `30x26` fit scoring only `77.679%` line / `84.934%` mesh and failed early-return safety because p90 reprojection error was too high. This supports the conservative safe-accept and compact-precision direction, but it is one fresh run on one hard source; keep it as evidence for more repeats, not a default promotion.

Two lower-cost `IMG_9717` follow-ups show the schedule tradeoff. A single `wave6` run was fast (`7.881s`) but selected a safe fit with only `82.267%` line / `95.74%` mesh, so fixed six is not a clear improvement. The `wave4_then2` shape is the better economy challenger: its first run stopped in wave one with four dot samples and scored `87.888%` line / `98.719%` mesh in `8.320s`; a repeat stopped in wave one again and scored `92.005%` line / `100.0%` mesh in `7.562s`; a second repeat found a one-dot safe fit in `6.482s` and finished in `7.218s`, but scored only `88.313%` line / `100.0%` mesh. Treat `wave4_then2` as the next lower-cost live candidate, but do not promote it yet. Promotion needs repeated hard-case runs around `<=10s`, usually stopping in wave one, with full-span line roughly `>=90%`, mesh `>=98%`, and no wrong-safe accepts. Demote it if repeats keep landing in the `85-88%` line band or if the early-return safety floor accepts label-weak geometries.

`IMG_9715` blocks promotion of the current `wave4_then2` safe/economy path. Before the large-span safety gate, the first-wave result passed the no-label safety floor but only scored `69.345%` homography-line and `81.95%` mesh alignment. The failure signature was a broad `32x24` span with low homography inlier ratio and elevated reprojection error. The safety floor now treats large-span fits with low inlier ratio plus elevated p90 reprojection error as unsafe. A fresh post-gate `IMG_9715` run found no safe accepted geometry before all six launched dots drained; with current `--require-safe-accept` semantics, that final unsafe accepted lattice is downgraded to `candidate-visible-lattice-geometry` rather than reported as accepted. This is the right product behavior: refusal/manual seed beats a wrong-safe projection.

The best fresh `IMG_9715` live result so far is fixed-five plus `guarded-risk-aware`: total wall `7.480s`, safe accepted geometry at `6.984s` after four completed dot reports, `99.167%` homography-line alignment, and `100.0%` mesh alignment. The raw first accepted geometry in the same run appeared earlier (`6.720s` after two dots) but scored only `73.157%` line / `88.146%` mesh and failed safety as a large-span low-ratio fit. The selected safe alternative was a smaller `23x12` visible-lattice fit; the separate manual seed remained the wider `29x31` fit.

The matching fixed-five `IMG_9717` run blocks broad full-span promotion. It returned quickly (`9.118s`) but the selected safe alternative scored only `77.466%` full-span line / `93.801%` mesh. Its observed-edge homography score was stronger at `95.384%`, so this is better understood as an observed-edge-only result than a completely wrong lattice. Its no-label signature was a mid-large `27x22` span with `0.507` homography inlier ratio and `0.048` p90 reprojection error. The safety floor now downgrades mid-large fits with low inlier ratio plus elevated p90 reprojection error, so the same artifact resolves to candidate under current `--require-safe-accept` semantics. Current recommendation: keep fixed-five `guarded-risk-aware` as an exploratory candidate, not a default; its safety gate improved full-span honesty, but it has not produced stable full-span quality across both hard sources.

A fresh `wave5_then3` run on `IMG_9717` did not exercise the second wave because the first wave produced a safe accepted result. It scored only `84.593%` full-span line, but `99.502%` observed-edge homography and `99.596%` observed mesh, with projection confidence `observed-edge-only` and recommendation `project-observed-region-only-until-extent-confirmed`. This changes the interpretation: the candidate may be useful for observed/confirmed grid regions, but it should not be treated as full-span map extent solved. The live runner summaries now print observed-edge homography, mesh, and projection-confidence fields so future speed runs are not judged by the full-span number alone.

The live runner now has an opt-in `--measure-early-accept` mode. It scores completed dot reports as they arrive after the line mask is available, records the first accepted geometry time, and still drains all launched jobs. This avoids unsafe API cancellation while measuring the possible upside of future early-return behavior. The runner caches the extracted line mask and per-dot fit results during a run so repeated early checks do not re-score old dots or renumber out-of-order dot jobs. Current evidence is mixed but improving: wave-five measurement accepted both `IMG_9719` and `IMG_9722` before full drain, while an earlier wave-three run on `IMG_9719` had no accepted geometry before drain and ended candidate.

The `IMG_9715` live run exposed a speed/quality failure mode: the runner found an early large `35x31` accepted lattice quickly, but benchmark truth showed only `62.942%` homography-line and `61.024%` mesh alignment. The no-label signature was borderline lower-quartile line support (`0.536`) combined with elevated coordinate conflicts (`11.633%`). The current fitter now demotes that combination to a candidate, which rescored the same live artifacts to the later first-wave `21x8` fit with `100.0%` line and mesh alignment. Early-return behavior must therefore use the same quality gate; do not return on the first merely accepted geometry if it has this borderline support/conflict signature.

A fresh `IMG_9715` run after that gate no longer returned a bad two-dot early accept. It waited until the first wave drained, then accepted a `27x17` visible lattice with `82.008%` homography-line and `94.558%` mesh alignment in `9.691s`. That is safer, but it also shows that early-return speed cannot be separated from quality gates.

The runner now records both first accepted geometry and first early-return-safe accepted geometry. Early-return-safe is a conservative latency floor over accepted fits: enough inliers and span, adequate homography inlier ratio, low reprojection error, high dot/line agreement, adequate fitted-line support, low coordinate conflicts, and enough observed inlier-mesh density. A fresh `IMG_9722` run shows why this matters: the first accepted one-dot fit appeared at `8.106s` but had only `89.423%` homography-line alignment and failed the safety floor because too few dots agreed with the independent line mask; the two-dot fit at `8.804s` passed the safety floor and scored `100.0%` line and mesh alignment.

The live runner now has an opt-in `--require-safe-accept` mode. With this flag, a wave-level accepted geometry does not stop the run unless it also passes the same early-return safety floor. This is the safer measurement mode for hard cases such as `IMG_9715`, where a quick accepted fit can still be lower quality than a later safe fit. Keep the default behavior available for historical comparison, but use `--require-safe-accept` when evaluating live-table candidate policies.

The live runner also accepts `--selection-policy guarded-mesh-density` and `--selection-policy guarded-risk-aware`. When `--require-safe-accept` is set, live wave selection can switch from an unsafe top accepted fit to the best safe accepted fit under the active selection policy, matching the replayed safe-streaming intent more closely. This path is help/compile verified and available for fresh API runs; it is not yet promoted as the live default.

The live runner now also accepts `--require-fullspan-accept`. With this flag, accepted visible geometry does not stop a run unless the selected fit is `no-label-full-span-candidate`; otherwise the result is downgraded to `candidate-visible-lattice-geometry` or the runner continues to the next wave. Three fresh checks validate both sides of the gate:

- `IMG_9715` fixed-five plus guarded risk-aware full-span mode finished in `7.436s` as `candidate-visible-lattice-geometry`; it refused full-span projection because the best geometry scored only `67.339%` full-span line / `77.167%` mesh.
- `IMG_9722` two-dot full-span mode finished in `6.304s` as candidate even though labels scored `100.0%` line and mesh, because no-label support was too weak for the runtime gate. This is conservative, not wrong-confident.
- `IMG_9722` fixed-five full-span mode accepted in `7.871s`, with first full-span-ready geometry after five completed dot reports. It scored `97.454%` line, `99.396%` observed-edge homography, and `98.161%` mesh.

Current interpretation: `--require-fullspan-accept` is the right live measurement mode for autonomous projection latency, but the strict no-label gate can refuse label-good geometries when the generated dot evidence is too sparse or uneven. Keep it opt-in while collecting more real-photo runs.

A fresh guarded live check on `IMG_9715` proved the flag path works but argues against promotion. The run accepted in `10.520s`, with the first safe accepted geometry at `8.696s`, but the selected safe fit scored only `72.642%` homography-line and `86.708%` mesh alignment. In the same run, an unaccepted candidate fit had better label alignment (`95.109%` homography-line / `98.592%` mesh) but failed the current auto/safe gate because its p90 reprojection error was `0.090` cells. Treat this as evidence that no-label safety gates are still imperfect on fresh generations: do not promote guarded mesh-density or early-return-safe acceptance until a candidate-aware quality proxy is tested on a larger corpus.

The stricter replayed safety floor also blocks the older unsafe `IMG_9715` one-dot artifact: it is still an accepted visible lattice, but it has only `0.279` homography inlier ratio and `0.142` observed mesh cell density, so raw `stream_wave3_then2` and `stream_fixed5` mark it not early-return-safe. `safe_stream_wave3_then2` waits for the later `dot-v03` fit, and `safe_stream_fixed5` can choose the smaller high-density `dot-v05` fit. This is a real speed/quality correction: early return is now gated by no-label coherence metrics, not just accepted status.

A fresh `IMG_9715` wave-five run after the inlier-ratio/mesh-density gate produced a safe early accept at `11.816s` after three completed dot reports and drained all launched calls at `13.013s`. The selected final five-dot geometry scored `97.764%` homography-line and `99.326%` mesh alignment, confirming that the stricter safety floor still permits useful live early acceptance on a hard case.

Do not implement true early return in the thread-based runner. `ThreadPoolExecutor` cannot safely cancel already-running blocking `requests.post()` image jobs, and the current artifact contract assumes each launched job eventually writes a report. If this remote AI path is ever promoted into the live calibration loop, build a separate subprocess-supervised runner: each API job writes through a temporary directory, completed job reports publish atomically, and the parent writes a final report listing completed, used, and terminated jobs before terminating outstanding child processes after a short grace. Even then, local termination cannot guarantee provider-side cancellation or billing rollback once a request has been accepted.

Recorded runtime notes below are historical replay/live measurements from the mixed artifact pool. Use the current summary tables above for current accuracy; use individual `parallel-report.json` files for clean live latency claims.

Recorded runtime on this corpus:

- one Grok white-line mask averaged about 5.9 seconds,
- Grok dots-only calls averaged about 6.6 seconds across the expanded run set,
- adaptive eight averaged 2.125 dots-only samples per image and about 20 seconds serial wall-clock per image,
- fixed five dots-only samples plus one line mask averaged about 9.1 seconds replay wall-clock if the API calls are issued in parallel, with higher API cost; first live hard-case check returned a strong candidate rather than auto acceptance.
- streaming fixed-five replay averaged about 6.5 seconds to first accepted geometry while preserving 8/8, but still launches the fixed-five API calls and requires product support for proceeding while background jobs drain.
- safe streaming fixed-five replay averaged about 6.6 seconds to first early-return-safe geometry while preserving 8/8 accepted and 8/8 safe choices, but still launches the fixed-five API calls and requires product support for proceeding while background jobs drain.
- parallel wave-three-then-two averaged about 9.8 seconds estimated wall-clock with lower API cost than fixed five.
- streaming wave-three-then-two averaged about 7.8 seconds estimated wall-clock with the same 26 launched-dot budget as parallel wave-three-then-two, but it also requires product support for proceeding while launched jobs drain.
- safe streaming wave-three-then-two averaged about 8.4 seconds estimated wall-clock with 28 launched dots and 21 completed dots before safe accept; this is the safer balanced replay speed-mode.
- parallel wave-two-then-one-then-two averaged about 12.7 seconds estimated wall-clock with lower API cost than wave-three-then-two.
- parallel wave-two plus line-skeleton gate, then three averaged about 11.0 seconds estimated replay wall-clock with the same dot-call count as wave-two-then-one-then-two, but its first live check fell back to dots and was slower than the speed default.
- A replay sweep of safe streaming wave schedules up to six dot samples did not find a faster safe policy than `safe_stream_fixed5`. Staged schedules such as `3,2`, `4,1`, and `2,3` can reduce launched calls, but they wait longer on current hard cases before a safe accepted geometry exists. Keep `safe_stream_fixed5` as the fastest replay policy and `safe_stream_wave3_then2` as the balanced lower-cost policy.
- replacing full pairwise neighbor matrices in the local fitter with OpenCV KNN preserved the selected variants and 8/8 accepted replay result while reducing one local replay from about `39.9s` to `35.7s` on this machine. This is not table-visible next to API latency yet, but it matters if dot counts or local-only candidate extraction grow.
- caching reusable line-mask distance/dilation products across dot variants preserved the selected variants and 8/8 accepted replay result while reducing one post-component-pool local replay from about `34.4s` to `33.2s` on this machine. This is small compared with API latency, but it is low-risk and helps repeated early-score checks.
- caching line-context and per-dot fit results inside the live runner reduced repeated scoring overhead for early-accept measurement and keeps dot variant IDs stable when API jobs finish out of order.
- a constrained line-mask angle prior now acts as a lazy rescue path when dot-neighbor axes do not produce an accepted fit. It does not override an already accepted dot-axis fit, and the fitter now skips the line-prior fit entirely for variants that already have an accepted dot-axis result. On the current artifact set it selected the line-mask prior for `2/8` final results (`IMG_9720`, `IMG_9721`), preserved `8/8` accepted, improved mean homography-line alignment from about `92.947%` to `93.114%`, and left mean mesh alignment effectively unchanged (`98.182%` to `98.177%`). The lazy version evaluated line-mask-prior candidates on `24/48` dot variants instead of every variant, preserving selected IDs and metrics. An unconstrained version was rejected because it overrode accepted dot-axis fits on `IMG_9715` and hurt mesh alignment.
- a lazy component-pool fallback was tested and not promoted. It evaluated only the largest connected lattice component first and skipped smaller components when the largest component already accepted. On the current corpus it preserved selected IDs and metrics, but skipped only `1/52` eligible component fits and did not produce a measured replay speed improvement. Keep the existing component-pool behavior as a robustness diagnostic rather than adding lazy-policy complexity.
- vectorizing segment-support sampling in the local edge builder preserved selected variants, manual-seed scores, and 8/8 accepted replay results while reducing one local replay to about `23.0s` on this machine. This is the first local-only speedup large enough to matter for repeated scoring and future low-power gateway tests, even though API latency still dominates the remote-AI path.

Accuracy on the selected `8/8` accepted run:

| Metric | Result |
|---|---:|
| Accepted visible-lattice geometries | 8/8 |
| Full-span homography line samples within 0.15 squares | 66.443%-100.0%, mean 90.532% |
| Observed-edge homography line samples within 0.15 squares | 87.224%-100.0%, mean 97.672% |
| Observed mesh line samples within 0.15 squares | 84.122%-100.0%, mean 96.829% |
| Benchmark projection readiness | 4 full-span auto, 1 full-span with manual extent check, 2 observed-edge-only, 1 manual confirmation |
| No-label projection readiness | 1 full-span candidate, 5 manual extent check, 1 observed-region candidate, 1 manual confirmation |
| Separate manual-correction seed selected | 6/8 |

Line-graph observed mesh on the same current line-mask artifact pool:

| Metric | Result |
|---|---:|
| Accepted observed-grid graphs | 8/8 |
| Observed mesh line samples within 0.15 squares | 89.482%-100.0%, mean 97.009% |

The gap between full-span homography and mesh metrics is partly a sampling-domain issue. OpenCV's camera calibration docs call out radial distortion bending straight lines, and mat curl may also matter, but the same-edge comparison shows that the homography usually agrees with the mesh over observed supported edges. The current evidence is better read as: full-span/extrapolated homography scoring can be harsh in less-supported parts of the lattice, while observed-edge evidence is much stronger.

The scorer now exports observed inlier-mesh vertices, edges, and complete cells for each selected fit. This does not make mesh projection the product default; it preserves the local evidence needed to test piecewise correction later without loosening the auto-accept gate.

The mesh-projection diagnostic no longer marks dot-consensus selected fits as a mesh-warp promotion candidate under the fair same-edge threshold. The current best-available guarded risk-aware dot summary scores `90.532%` mean / `66.443%` min full-span homography, `97.672%` mean / `87.224%` min observed-edge homography, and `96.829%` mean / `84.122%` min observed mesh. The newer line-graph path scores `97.009%` mean / `89.482%` min observed mesh from one line mask, so mesh/graph evidence should remain an active branch even though unsupported full-span extrapolation is still unsolved.

Under the guarded mesh-density policy, full-span homography scores `96.809%` mean / `81.293%` min, observed-edge homography scores `99.077%` mean / `92.617%` min, and observed mesh scores `99.396%` mean / `95.362%` min. The same-edge mesh gain averages `0.319` points, maxing at `2.745` points. This makes visible-region mesh warp a lower-priority implementation candidate than the earlier full-span numbers implied. The stronger next problem is deciding how much unsupported full-span extrapolation to trust, and how to expose observed-edge confidence without pretending full mat extent is solved.

Under the current guarded risk-aware policy, the best-available artifact pool preserves `8/8` accepted visible lattices. The final `IMG_9717` fix is a high-precision compact challenger: when a broad accepted lattice has weak support and a cleaner compact accepted patch exists, the selector can prefer the compact patch. This moves `IMG_9717` to a `20x18` patch with `93.86%` full-span line and `100.0%` mesh alignment. The tradeoff is coverage: this is a high-quality observed/confirmed-region seed, not proof that the full mat extent is solved.

Projection readiness is stricter than geometry acceptance. The current benchmark readiness is `4/8` full-span auto, `1/8` full-span with manual extent check, and `3/8` observed-edge-only. The no-label runtime gate is stricter again: `1/8` full-span candidate, `5/8` manual extent check, `1/8` observed-region candidate, and `1/8` manual confirmation. It has `0/8` dangerous disagreements where no-label would auto-project but benchmark readiness would not. This is the right posture for now: the grid family is found on all eight images, but most cases still need extent confirmation before autonomous full-span projection.

Retry-policy summaries now report no-label readiness counts in addition to geometry decisions. This matters because several policies still show `8/8` accepted visible geometries while only `3/8` or `4/8` choices are no-label full-span auto candidates. In the guarded risk-aware replay, `parallel_wave3_then2` remains a fast visible-lattice policy at about `9.8s` average wall time, but only `3/8` of its choices are no-label full-span candidates. `parallel_fixed5` and `safe_stream_fixed5` reach `4/8` no-label full-span candidates; `safe_stream_fixed5` estimates about `6.6s` average wall time because it stops as soon as early-return-safe geometry appears. These numbers are not final product policy yet; they make the next speed comparison honest about whether the result is auto-projectable or only a manual/observed-region seed.

The replay report now also includes projection-ready streaming policies. `fullspan_stream_fixed5` waits for no-label full-span projection-ready geometry when one appears among the launched fixed-five jobs; it keeps the same `4/8` strict full-span candidates, uses `36` launched dot samples, completes `25`, and estimates about `7.1s` average wall time. `fullspan_stream_wave3_then2` also keeps `4/8` strict full-span candidates but estimates about `11.0s` average wall time. The useful conclusion is not that projection-ready streaming improves accuracy; it gives a more honest latency number for the subset of cases where the system can auto-project without manual extent confirmation.

The scorer also includes a benchmark-only no-label readiness sensitivity sweep. The current strict no-label gate gives `4/8` full-span candidates with `0` dangerous benchmark disagreements. Three relaxed gates show possible headroom without changing runtime behavior: `small-span-relaxed-v1` reaches `5/8` by promoting `IMG_9719`, `clean-subspan-v1` reaches `6/8` by also promoting a cleaner `IMG_9721` subspan, and `medium-density-v1` reaches `7/8` by also promoting a safer `IMG_9716` variant. All three relaxed gates have `0` dangerous disagreements on this corpus, but they are not promoted because the corpus is small and the hard `IMG_9717` variants show how easy it is for plausible clean local evidence to be wrong over full span.

Observed-edge-only means the homography scores well on supported observed mesh edges, but full-span scoring drops enough that projection should stay limited to observed/confirmed regions until extent is manually or otherwise confirmed. On the current corpus, guarded mesh-density is useful because it removes the `IMG_9715` full-span-risk case, but it does not solve `IMG_9717`. That keeps guarded mesh-density as a promising challenger, not the default.

The scorer now also reports accepted-only mesh-density selection diagnostics. These compare the current auto selection against denser accepted variants, but they do not change auto selection or acceptance. The raw highest-density diagnostic differs from auto selection on `4/8` images and would raise the label-scored average homography-line alignment, but it can prefer smaller dense patches and worsens at least one currently perfect fit (`IMG_9722`). A stricter guarded diagnostic requires an accepted challenger to be early-return-safe, materially denser, and at least 35% of the auto span. On the current artifact set it differs only on `IMG_9715`, improving that scored fit from `70.44%` homography-line / `90.094%` mesh alignment to `100.0%` homography-line / `99.845%` mesh alignment. Keep both diagnostics report-only until a larger corpus proves that selecting smaller dense patches is a safe projection default rather than an overfit benchmark improvement.

The guarded mesh-density challenger is now runnable but still not the default:

```bash
npm run benchmark:ai-grid-current-guarded-mesh-summary
npm run benchmark:ai-grid-current-risk-aware-summary
```

This policy starts from the normal highest-confidence selection, then may switch to an early-return-safe accepted variant with materially denser observed inlier mesh and enough span. It uses only no-label geometry metrics; labels are still benchmark-only. On the current eight-image corpus it preserves `8/8` accepted, changes only `real-map-home-IMG_9715.jpg` from `dot-v03` to `dot-v05`, improves mean homography-line alignment from `93.114%` to `96.809%`, improves mean mesh alignment from `98.177%` to `99.396%`, and raises the minimum mesh score from `90.094%` to `95.362%`. The scorer's retry-policy summaries now honor the selected policy; for example, the guarded `fixed5` and `parallel_fixed5` choices for `IMG_9715` select `dot-v05` instead of the confidence policy's wider `dot-v03`. The tradeoff is coverage: `IMG_9715` shrinks from a `28x25` visible lattice to a `24x11` denser patch. Treat this as an accuracy challenger for the larger corpus, not a promotion.

The guarded risk-aware policy starts from guarded mesh-density, then applies narrow ambiguity challengers. The current most important challenger is high-precision compact selection: if the selected lattice is broad but weakly supported, a smaller accepted patch can win when it has materially better line support, enough cells, moderate conflicts, enough span, and a close no-label score. This was added after fresh hard-case runs exposed no-label selector misses where the highest-score accepted lattice had many inliers but poor observed-mesh alignment. A re-score of the `IMG_9719` wave-eight artifact set now selects compact `dot-v03` (`17x17`, line `99.877%`, mesh `100.0%`) instead of the broader weak fit. This is useful evidence that selector quality, not only retry count, matters.

The hybrid summary can now accept multiple line-graph reports and apply a narrow prompt/input ensemble selector. The default line prompt remains the safest single prompt, but the short solid-line prompt and one larger-input retry are useful on some images. On the current artifacts, the ensemble replaces the default line graph only for `IMG_9715` and `IMG_9720`, where the alternate graph has better no-label graph density, node fill, coordinate conflicts, span, and score gates. `npm run benchmark:ai-grid-hybrid-prompt-ensemble-summary` improves the selected-line mean/min from `99.393%` / `95.964%` to `99.973%` / `99.882%` while still using dot consensus on `2/8` sources. This is report-only; it should not become runtime default until a larger real-camera corpus proves that prompt/input retries do not overfit this mat.

The current product interpretation separates lattice alignment from mat-boundary ownership, as recorded in [ADR-002](../decisions/adr-002-grid-detection-alignment-frame.md). `npm run benchmark:ai-grid-frame-summary` keeps the selected prompt-ensemble homography exactly as-is, but replaces the old supported/boundary-seeking extent with a bounded image-frame grid: expand the detected lattice across the source image, cap each axis at `100` cells, then trim edge rows or columns whose sampled band has less than `10%` source-photo overlap. On the current eight real-home labels, the old selected extents covered only `27.393%` mean / `10.727%` min of visible human-labelled intersections because they preferred small clean support patches. The bounded frame extents cover `99.95%` mean / `99.598%` min, stay inside the `100x100` cap, and avoid keeping pure sliver/dead-space bands. A material-aware visible-mask cue was tried and rejected because real shadows can make valid grid look like non-material. This does not prove the physical mat boundary; it supports the simpler MVP framing that the grid is primarily an internal alignment coordinate frame and the DM can decide how much map to place on it.

The current guarded risk-aware best-available summary still has benchmark-only oracle headroom on `IMG_9715` and `IMG_9721`. The report shows `2/8` material best-composite misses, mean composite headroom `3.415` points, and max headroom `18.815` points. Do not feed oracle choices into runtime selection; use them to design no-label quality proxies for the next larger corpus and to evaluate the observed-grid graph branch.

The report now includes benchmark-only oracle diagnostics. These use saved labels only after selection to show whether the generated artifact set contained a more accurate variant than the no-label selector chose. They must not feed runtime selection. The current material misses are `IMG_9715`, where the best label-scored dot variant is only a candidate but improves observed mesh from `84.122%` to `100.0%`, and `IMG_9721`, where another accepted variant improves full-span line alignment from `86.71%` to `99.927%`. This confirms the next accuracy problem is not retry count; it is no-label selection quality when multiple plausible lattices exist.

The report now also includes no-label accepted-variant ambiguity diagnostics. These compare the selected accepted fit against nearby accepted challengers without changing runtime selection: score gap, span-area ratio, inlier/ratio deltas, p90 error deltas, line-support deltas, coordinate-conflict deltas, observed mesh density, early-return safety, score-contribution deltas, symmetric lattice agreement between accepted variants, and high-precision compact challenger matches. This catches the current `IMG_9717` problem shape: selected `dot-v07` has borderline reprojection error plus high coordinate conflicts, a wider accepted challenger has a similar no-label score, and the fuller same-error diagnostic points to `dot-v04`, which is `+6.877` composite points by label. The broad fuller same-error heuristic is not promotable: under the confidence policy it appears on `3/8` images with two positive benchmark deltas and one negative delta (`-5.493`), while under guarded mesh-density it has one positive and two negative deltas, including a large `IMG_9715` regression (`-18.261`). The narrower guarded risk-aware policy is the promoted replay challenger for this idea, but it still needs a larger real-capture corpus before becoming default.

The fitter now evaluates the top lattice components inside each dot variant instead of blindly trusting only the largest connected component. On the current artifact set this did not improve the selected final result: `45` variant component pools were evaluated, `2` variants selected a non-largest internal component, and `0/8` final selected results used a non-largest component. Keep the component pool as a robustness hook and diagnostic; it is not an accuracy improvement on this corpus.

The fitter also evaluates a line-mask angle prior as an alternate axis source for the dot graph. The promoted behavior is deliberately constrained and lazy: when dot-neighbor axes already produce an accepted fit, keep that fit and do not spend CPU on the line-prior candidate; use the line-mask prior only as a rescue candidate for dot variants whose dot-axis fit is candidate/refused. This matters because a naive "highest no-label score wins" version selected the line prior for `4/8` final results but worsened `IMG_9715` mesh alignment from `90.094%` to `86.387%`. The constrained version selects line-prior rescues only for `IMG_9720` and `IMG_9721`, where it improves homography-line scoring without creating a lower minimum score. The current report records `72` axis-candidate fits across `48` dot variants, with line-prior evaluation on `24` variants; the earlier always-evaluate shape would have spent `96` axis-candidate fits on the same corpus.

The current acceptance rule includes a compact high-support lane for visible patches that have high absolute inliers, very low reprojection error, strong dot-line agreement, strong line support, enough span, and low coordinate conflicts despite a lower homography inlier ratio. This reduced required retries without using fixture labels in selection.

The acceptance rule also demotes otherwise accepted fits when lower-quartile fitted-line support is borderline while coordinate conflicts are elevated. This targets live outputs where an overly broad lattice looks internally strong because it has many inliers, but the fitted line family is not uniformly supported and the coordinate graph is noisy. The gate preserved `8/8` accepted on the current artifact corpus and fixed the `IMG_9715` live-run artifact described above.

## Line-Only Challenge Results

The line approach remains attractive because a single line mask is cheaper than repeated dots-only calls and should, in principle, make every gridline visible. The current blocker is local parsing and model consistency, not the concept.

Three follow-up probes tested this directly:

- `npm run benchmark:ai-line-skeleton` skeletonizes the single white-line mask, extracts branch-point junctions, and reuses the deterministic dot-lattice fitter. Current checks keep it below dot consensus; it remains the best no-extra-dot-call line-only helper, not a replacement.
- `npm run benchmark:ai-line-graph` skeletonizes the single white-line mask, treats junctions and line runs as a graph, assigns local grid coordinates by graph traversal, and scores observed mesh edges directly. Current checks reach `6/8` accepted and `2/8` candidate observed-grid graphs, with mean `97.958%` and min `89.073%` observed-mesh alignment. Its report-only grown-extent gate lifts selected-line mean/min to `98.820%` / `95.413%`. This is the strongest line-only path so far, but it is observed-region or report-only grown-extent evidence rather than full-span runtime proof.
- `npm run benchmark:ai-line-graph-solid` replays the short solid-line prompt. Alone it is worse than the default prompt (`5` accepted, `2` candidate, `1` refusal), but it gives cleaner local graph evidence on `IMG_9715` and `IMG_9720`, making it useful as a prompt-retry ensemble member.
- `npm run benchmark:ai-line-graph-solid-w1600` replays the short solid-line prompt from a larger working-input retry. It improves `IMG_9715` from `99.507%` to `99.882%` after tightening grown-extent trust, but it worsens `IMG_9720`. Keep it as a guarded retry, not a global replacement.
- `npm run benchmark:ai-family-pair` directly tests the two-image family idea: one AI output for one line family, one for the crossing family, then local Hough clusters are intersected. Current checks show the local assembly can work when masks are clean, but Grok often draws the same family twice, draws both families, or changes geometry. It is not stable enough to replace white-line plus dot consensus.

Use the graph parser as a possible low-cost observed-region/mesh-warp fast path from an already generated white-line mask. Do not make it the live-table default yet: it needs more real-camera evidence, a better extent story, and a product decision about whether observed mesh projection is acceptable before full-span homography is solved.

## Rejected Branches

These branches were tried after the first AI recipe checkpoint and are not current defaults:

- Separate less-steep and more-steep line-family masks: sometimes useful, but one side often redraws the full grid or includes pencil/room marks. This remains a possible future refinement, not a replacement for dots.
- Full-corpus separated stripe-family masks: `npm run benchmark:ai-family-stripes` scored `0/16` usable lattice seeds under `test-results/ai-mask-lattice-probe-family-stripes-v2-full/`. The model often drew both families, selected the wrong family, or mixed non-grid marks.
- Visual slant stripe prompts: down-right/up-right wording was tested on three diagonal hard cases and scored `0/6` usable seeds under `test-results/ai-mask-lattice-probe-family-slant-v1/`. The masks often had good foreground alignment but still did not isolate one family reliably enough for local lattice parsing.
- Single-mask Harris junction extraction: `npm run benchmark:ai-line-junction` scored `4` candidate visible geometries and `4` refusals, with `0/8` accepted under `test-results/ai-line-junction-probe-v1/`. Extracting junctions from the white-line mask creates too many duplicate/ambiguous points for the current local graph fitter.
- Single-mask skeleton junction extraction: `npm run benchmark:ai-line-skeleton` improved the line-only path to `4` accepted, `3` candidate, and `1` refusal, but still falls short of the `8/8` dot-consensus recipe and the newer observed-grid graph parser.
- Ordered line-family/intersection fitting: `npm run benchmark:ai-line-lattice` scored `2` candidate visible geometries and `6` refusals, with `0/8` accepted under `test-results/ai-line-lattice-ransac-v1/`. This removes the dot-neighbor graph and assigns coordinates from ordered Hough line IDs, but the AI line masks still fragment/duplicate enough lines that line-only inlier ratios and truth alignment remain weaker than dot consensus.
- Projection-profile line recovery: the ordered line-family fitter now also tests whole-line peaks from mask projection profiles instead of Hough segment clusters alone. The replayed result remained `2` candidate visible geometries and `6` refusals; the profile mode won selection on one refusal but did not promote any image. This suggests the current line-only blocker is generated-mask consistency and family ownership, not only Hough fragmentation.
- Inlier-line refinement for the ordered line-family fitter: after a first RANSAC fit, the probe prunes line IDs that do not participate in enough inlier intersections and refits. It improved one internal `IMG_9720` refusal's truth-line score to `80.952%`, but it did not change the promoted result: the line-only eval remains `2` candidates, `6` refusals, and `0/8` accepted.
- Paired single-family line masks: `npm run benchmark:ai-family-pair` scored `1` accepted, `4` candidate, and `3` refusal. This is the fairest current test of the two-family idea and it remains promising as a manual seed, but the model's family isolation is not stable enough to replace white-line plus dot consensus.
- Concise horizontal/vertical family prompts: tested on `IMG_9715`, `IMG_9717`, and `IMG_9719`; paired-family parsing refused all three because the model frequently drew the same family twice or did not isolate a family cleanly.
- Existing explicit less-steep/more-steep stripe prompts: retested on the same three hard samples; paired-family parsing produced `1` accepted, `1` candidate, and `1` refusal, but label-scored full-span line alignment stayed around `52-66%`. This is not worth more API spend until the model can reliably isolate one family.
- Removing the independent AI white-line mask was probed against the existing dot artifacts with `npm run benchmark:ai-dot-only`. The dot-only optimistic run reached `5` accepted and `3` candidate visible lattices, with mean full-span line `85.025%` and mean mesh `89.268%`. The separate AI white-line evidence remains part of the current default because it provides useful dot filtering, line support, and axis-prior evidence.
- Dots generated from the Grok line mask: tested on `IMG_9715`, `IMG_9717`, and `IMG_9719` with a dedicated line-mask-to-intersections prompt. It produced many spurious dots and scored only `2` candidate plus `1` refusal, so line-to-dot is worse than dots generated directly from the original photo.
- Concise dots-only prompt: tested on `IMG_9715`, `IMG_9716`, `IMG_9717`, and `IMG_9719`; it produced only candidate results under both current and fresh line masks and was weaker than the current intersection prompt.
- Stricter/freehand-exclusion line prompts: tested on hard samples. They sometimes removed non-grid drawing marks, but they also removed or distorted real grid evidence. The simpler original white-grid prompt remains the default; line-mask retries may help, but prompt replacement is not justified.
- Exact short line prompt close to the user's suggested wording (`white-grid-actual-only-no-occluders-v7`): tested on the remaining near-misses `IMG_9715` and `IMG_9720`; line-graph scores were `93.836%` and `98.198%`, worse than the solid-line retry.
- Direct JSON grid extraction with OpenAI, Gemini, and Grok: tested on `IMG_9715` and `IMG_9720`; all three providers missed row/column counts and produced mean/max corner errors around `8-17` grid squares. Direct JSON is not competitive with generated mask plus local geometry parsing.
- Full-resolution solid-line input retry on `IMG_9720`: Grok still returned an `880x1168` output and line-graph scoring dropped to `98.052%`, worse than the current `99.903%` solid-line graph.
- Local default/solid mask fusion for `IMG_9720`: union, intersection, and simple composite masks all parsed worse (`83.186%`, `93.782%`, and `92.55%`) than the current solid-line graph. The remaining `99.903%` case is not improved by naive local mask algebra.
- Extra Grok solid-line samples for `IMG_9720`: one candidate in the batch scored `100.0%` by label, but its no-label score, span, cells, edge density, node fill, and conflicts were all weaker than the selected `99.903%` graph. Do not select it automatically; that would be label overfit.
- Merging dots across multiple AI samples was probed as a possible retry reducer. A support-2 clustered consensus over the first 2, 3, 4, and 5 dot samples scored only `3/8`, `1/8`, `1/8`, and `1/8` accepted respectively, with many wide candidates or refusals. The merged sets add duplicate/noisy intersections faster than they create a cleaner lattice, so the current best-of-sample retry logic remains stronger.
- Truth-free selection-score retuning was probed against the selected report. A line-support-heavy heuristic improved label-scored average line alignment from `92.95%` to `94.55%` and the minimum from `70.44%` to `83.14%`, but it often achieved that by choosing smaller patches, such as `IMG_9715` shrinking from `28x25` to `24x11`. Wider-span and manual-seed-style heuristics generally made average and minimum truth scores worse. Keep the current balanced selection score and the separate manual-correction seed rather than overfitting auto selection to this corpus.
- Accepted-only mesh-density selection is promising but not promoted. Under the confidence policy, the report-only `accepted_mesh_density` diagnostic differs from auto selection on `4/8` images and scores `96.229%` mean / `81.293%` minimum homography-line alignment and `99.0%` mean / `95.362%` minimum mesh alignment, but it achieves some of that by selecting smaller dense patches and worsens `IMG_9722` from a perfect auto fit. Keep it as a monitored diagnostic rather than an auto selector.
- Large/exhaustive intersection dots: sparse or empty on hard cases.
- Combined gridlines plus brighter intersections: useful-looking visual output, but weaker than the existing white-line prompt as fitter input.
- Red/blue axis color: useful foreground only; not axis metadata.
- Centroid-only intersection dots prompt: first hard-case run on `real-map-home-IMG_9719.jpg` matched only `17/867` visible intersections, so it was rejected before a full corpus run.
- Pink overlay prompt: first hard-case run on `real-map-home-IMG_9719.jpg` preserved aspect but scored worse than the current white-line mask (`56.793%` <=0.10-square foreground alignment versus the current white-line mask's `76.929%`), so it was not promoted.

## Commands

Generate a line mask for one labeled source:

```bash
uv run --python 3.12 --with requests --with opencv-python-headless --with pillow --with numpy python scripts/ai-grid-experiment.py --source-id real-map-home-IMG_9717.jpg --providers grok-image --prompts white-grid-exact-copy-no-marks-v1 --out-dir test-results/ai-grid-experiments-grok-white-v1/real-map-home-IMG_9717
```

Generate one dots-only sample for one labeled source:

```bash
uv run --python 3.12 --with requests --with opencv-python-headless --with pillow --with numpy python scripts/ai-grid-experiment.py --source-id real-map-home-IMG_9717.jpg --providers grok-image --prompts white-intersection-dots-no-lines-v1 --out-dir test-results/ai-grid-experiments-grok-dots-realhome/real-map-home-IMG_9717
```

Re-score the current selected artifact set:

```bash
npm run benchmark:ai-grid-current
npm run benchmark:ai-grid-current-summary
npm run benchmark:ai-grid-current-guarded-mesh-summary
npm run benchmark:ai-grid-current-risk-aware-summary
npm run benchmark:ai-line-graph
npm run benchmark:ai-grid-hybrid-summary
npm run benchmark:ai-line-graph-solid
npm run benchmark:ai-line-graph-solid-w1600
npm run benchmark:ai-grid-hybrid-prompt-ensemble-summary
```

The scorer command uses labels only for benchmark fields. Selection is based on no-label geometry metrics. Use `benchmark:ai-grid-current` when you need overlays/contact sheets for visual inspection, `benchmark:ai-grid-current-summary` for fast metric-only iteration, `benchmark:ai-grid-current-guarded-mesh-summary` to evaluate the opt-in dense-patch selection challenger, `benchmark:ai-grid-current-risk-aware-summary` to evaluate the opt-in guarded density plus risk-aware fuller/compact challengers, `benchmark:ai-line-graph` to evaluate the one-line-mask observed-grid graph branch, `benchmark:ai-grid-hybrid-summary` to evaluate the report-only no-label hybrid selector, and `benchmark:ai-grid-hybrid-prompt-ensemble-summary` to evaluate the short-prompt ensemble gate.

Run the current live parallel recipe for one source:

```bash
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9719.jpg
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9722.jpg --waves 2,1,2
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9715.jpg --waves 5 --selection-policy guarded-mesh-density --require-safe-accept --summary-only
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9722.jpg --waves 5 --selection-policy guarded-risk-aware --require-fullspan-accept --measure-early-accept --summary-only
npm run benchmark:ai-grid-parallel-current -- --source-id real-map-home-IMG_9717.jpg --waves 5 --selection-policy guarded-risk-aware --summary-only
npm run benchmark:ai-grid-parallel-hybrid -- --source-id real-map-home-IMG_9717.jpg
npm run benchmark:ai-grid-line-first-current -- --source-id real-map-home-IMG_9716.jpg --summary-only
npm run benchmark:ai-grid-line-first-current -- --source-id real-map-home-IMG_9719.jpg --summary-only --require-safe-accept
```

Run the line-only probes:

```bash
npm run benchmark:ai-line-junction
npm run benchmark:ai-line-lattice
npm run benchmark:ai-line-skeleton
npm run benchmark:ai-family-stripes
npm run benchmark:ai-family-pair
```

## Current Recommendation

Adapt the AI-assisted seed path, but do not promote it as autonomous full-mat projection.

The current best practical use is:

1. Use the Grok white-line observed-graph path as a low-cost seed when the line mask is already available.
2. For live-table speed, keep speculative dots in the plan until serial line-first proves it can avoid fallback often enough.
3. Use Grok white-line plus dots-only evidence to find the correct visible lattice when line graph alone is not accepted/trusted.
4. Offer the supported patch as the safest automatic seed candidate.
5. Offer selected-fit and wider/manual spans as human-review correction starts.
6. Use the support-cell overlay to show which rectangular grid regions are backed by actual observed evidence.
7. Keep label-sized diagnostic mode only for eval/labelling because it uses saved ground truth.

This is acceptable for the next prototype step as a manual-confirmation aid. It is not yet acceptable as a no-review Project button because extent ownership remains unresolved. The next algorithmic gains should target mat extent, border/usable-area ownership, and confidence around unsupported cells, not basic lattice orientation.

## Acceptance Rules

Keep these rules until real hardware evidence proves a better contract:

- wrong-confident projection remains worse than refusal,
- generated images are evidence, not authority,
- accept only when dots agree with the independently generated line mask,
- accept lower homography inlier ratios only when absolute inliers, reprojection error, line agreement, line support, and conflict metrics are all strong,
- demote borderline support plus elevated coordinate-conflict fits before considering early return,
- keep auto geometry and manual-seed geometry separate,
- refuse full extent unless the app has dimensions, borders, or manual confirmation,
- remote AI must stay optional for live play.

## Next Proof

The next useful proof is a larger real-camera corpus: more lighting conditions, camera angles, curl, glare, shadows, foreground objects, and actual table captures. Run the same recipe and compare against OpenCV, active calibration, and manual-seed workflows before promoting remote AI into product architecture.
