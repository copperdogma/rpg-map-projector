---
{
  "title": "Active Projector-Camera Calibration Pattern Spike",
  "status": "Draft",
  "priority": "High",
  "origin": "Projection-mapping scouting and synthetic active-calibration experiments found a promising one-frame projected fiducial/circle pattern, but the current active work must return to printed mat-grid detection. Preserve the active-calibration branch as a deferred hardware spike so it is not lost.",
  "ideal_refs": ["docs/ideal.md"],
  "spec_refs": ["spec:2.1", "spec:6.1", "spec:7.1"],
  "depends_on": ["001"],
  "category_refs": ["spec:2", "spec:6", "spec:7"],
  "compromise_refs": ["B3", "B7"]
}
---

# Story 004: Active Projector-Camera Calibration Pattern Spike

## Goal

Prove, on real projector/camera hardware, whether a projected known calibration pattern can map projector pixels to camera/table coordinates faster and more reliably than passive projector alignment alone.

This is goal 2: active projector-camera calibration. It does not replace the current goal 1 work of detecting the printed battle-mat grid in camera/photos.

## Deferred Status

This story is intentionally Draft/deferred until hardware is available or Story 001 reaches the projector/camera physical pass. Do not keep expanding this branch while the active work is printed mat-grid detection.

This is a preservation story, not the active implementation lane. Its purpose is to keep the projection-mapping/active-calibration discoveries findable so a future agent can resume them without rediscovering the same pattern families, failure modes, and synthetic results.

Current parking decision: keep this story Draft until physical projector/camera hardware exists or the active grid-detection lane explicitly needs a projector-to-camera transform proof. Do not activate it merely because passive/AI grid detection work is hard; activate it when the work needs to solve where projector pixels land on the table.

Activate this story when at least one of these is true:

- an HDMI projector and fixed camera source are attached to the laptop gateway,
- a Raspberry Pi or other gateway candidate is available for calibration timing,
- printed-grid detection has a usable mat-grid result and the remaining blocker is projector-to-camera mapping,
- physical evidence shows sparse homography, camera correction, or projector correction needs a dedicated active-calibration pass.

## Lane Boundary

This story exists because a useful projection product needs two different transforms:

1. the printed mat/grid to camera/table transform, owned by the active grid-detection stories, and
2. the projector pixels to camera/table transform, owned by this deferred active-calibration story.

Do not treat success in one layer as proof of success in the other. AI-generated line masks, dot consensus, passive OpenCV probes, and labeled mat photos belong to Story 003 unless they are being used only as verification inputs for the projector-camera transform. Projected fiducials, projected circles, setup cards, projector compensation, camera/rig profiles, frame IDs, and physical projected-pattern residuals belong here.

The intended future integration is layered: find or confirm the mat grid, solve or validate the projector-camera mapping, then warp the prepared map into projector pixels. If a future agent resumes this story, it should preserve that split instead of turning active projection calibration into another passive printed-grid detector.

Related AI-mask and image-generation experiments belong to the printed-grid detection lane unless they are only being used as analysis inputs for this active transform. An AI-generated overlay of the battle-mat grid may help locate the mat grid in a photo; it does not by itself solve where projector pixels land on the table. Conversely, a projected known pattern may solve the projector-camera mapping without identifying the printed mat's rows and columns. Keep those layers separate in code, evals, and documentation.

## Handoff Summary

When this story resumes, start from these conclusions rather than re-litigating the branch:

- The useful architecture is layered calibration: camera profile, fixed projector-camera rig profile, per-session mat/grid acquisition, then a manual fallback/verification layer.
- The active-calibration problem is not "detect an arbitrary grid." The gateway projects known geometry, captures it, and solves explicit projector-to-camera correspondences.
- The current synthetic leader is a one-frame pattern with perimeter coded fiducials plus interior circle targets.
- The current first hardware challenger is marker-seeded projected line evidence: separate horizontal/vertical or sparse encoded line frames may be easier for local CV, but only if correspondences are explicit enough to avoid anonymous repeated-grid ambiguity.
- The dots/circles are not valuable because local code wants to assemble anonymous points into a grid. They are valuable because their projector coordinates are known and marker IDs can seed correspondence, giving precise feature centers for an overdetermined homography or residual check.
- The line idea should be tested because long connected line supports may survive projector blur/glare better than small circles and may be cheaper to parse. It should beat the circle path on physical residual or timing before it displaces the synthetic leader.
- Camera undistortion and projector-profile awareness are part of the calibration problem, not optional polish. Without them, curved residuals can be misdiagnosed as bad target detection.
- Synthetic pixel residuals are only a ranking signal. The first real success metric is physical projected alignment error in inches or fractions of a 1-inch square within the live-table time budget.
- Keep the live path local-first on the gateway. Remote AI/storage may exist elsewhere in the product, but this transform must not require cloud availability.
- If future work adopts ArUco/AprilTag/ChArUco, dense structured light, a native OpenCV runtime, or a mesh-warp model as durable architecture, create or update an ADR before locking it in.

## Background

Projection-mapping systems project known patterns, observe them with a camera, and solve how projector pixels land in camera or surface coordinates. RPG Map Projector can borrow that mechanic because the gateway controls the projector output and camera input.

The product still needs the physical mat grid in camera/table coordinates. Active projector-camera calibration answers a separate question: once the system knows a desired table/mat coordinate, which projector pixels should light up?

That distinction is the reason this story is parked instead of folded into the current grid-detection loop. Goal 1 locates the printed battle-mat grid in camera/photo space. Goal 2 maps projector output to the camera/table scene. A useful physical product needs both layers; neither layer proves the other.

## Captured Value From The Deferred Branch

Do not lose these findings when this story is resumed:

- Projection-mapping research is valuable as a calibration architecture pattern, not as a reason to adopt a generic VJ/projection-mapping app.
- The clean split is: detect or confirm the physical mat/grid, calibrate projector pixels to camera/table coordinates with active projected evidence, then warp the prepared map into projector pixels.
- Active projector-camera calibration does not remove the need to know the mat/grid in the current scene. It solves a different transform layer: projector pixels to camera/table coordinates.
- Keep the implementation local-gateway-first. Remote AI and remote storage may help other workflows later, but this calibration layer must be able to run at the table without depending on an internet service.
- Projected known-ID markers avoid the core ambiguity of passive repeated gridlines because correspondences are explicit.
- Interior projected circles/dots are more precise than marker corners when detected cleanly, but anonymous dots need a seeded correspondence model.
- The best synthetic compromise so far is a one-frame composite: perimeter coded fiducials for identity and interior circle targets for dense surface accuracy.
- The deeper pattern is "explicit identity anchors plus dense geometric targets." Marker IDs solve correspondence; circles, corners, or lines improve residual/surface coverage.
- Projected-line-only targets may be easier to segment than dots, but a plain repeated line grid reintroduces the same indexing and ownership ambiguity as passive battle-mat grids. If line targets are tested, they should be encoded, swept, Gray-code-like, or marker-seeded rather than treated as anonymous one-frame gridlines.
- A marker-seeded line target is still worth testing on hardware because projected lines may survive blur and glare better than small circles. Treat it as a challenger, not as the current synthetic leader.
- The strongest line-target argument is local simplicity: if the captured active frame contains only horizontal projected lines, or only vertical projected lines, local CV can extract long connected supports instead of assembling dots into a lattice. That is worth measuring. The risk is correspondence: without IDs, phase, sweep order, marker anchors, or another indexing cue, the solver may know the line family but not which projector line each observed line represents.
- A practical line challenger should therefore be one of: perimeter-marker seeded horizontal/vertical line frames, two separately projected H/V frames with visible frame IDs, swept indexed lines, sparse encoded line families, or a point-plus-line homography using markers/circles for identity and long lines for residual strength.
- Masking detected marker regions before circle extraction is essential; otherwise white marker cells can be misread as circle targets.
- The target-adapted two-frame fiducial-plus-circle branch is the best fallback if one-frame mixed features fail under real projector blur, glare, or exposure.
- Target-adapted closed-loop calibration has a specific research basis: estimate rough geometry first, then project high-value features where the target/camera can see them cleanly.
- ChArUco remains the mature OpenCV fallback challenger because it combines marker IDs with interior chessboard-like corners.
- AprilGrid, checkerboard-SB, and setup-card targets are controlled-target fallbacks. They are not passive arbitrary-battle-mat detectors, but they may simplify a real hardware setup/profile pass.
- Plain fiducials are robust and fast but weaker for full-surface accuracy; they are still useful as a seed or sanity check.
- Decimated global detection plus full-resolution ROI/subpixel refinement is the default Raspberry Pi benchmark shape to try once hardware exists: find markers/circles/corners cheaply, then spend full-resolution work only on accepted feature neighborhoods.
- ECC/direct image-alignment refinement is a post-seed challenger, not a seed. Use explicit marker/circle correspondences first, then let image alignment refine only if holdout residuals improve.
- A-contrario/VSAC-style adequacy gates are worth adapting as refusal logic because wrong-confident projector mapping is worse than manual fallback.
- Mixed point-and-line homography is a hardware challenger if projected lines survive blur/glare better than circles. It should be marker-seeded or otherwise indexed, not anonymous repeated lines.
- Symmetric/asymmetric circle grids are precise when accepted but less robust because correspondence and missing-point handling are harder.
- Camera undistortion is not optional once physical residuals matter. Distorted camera frames can make straight-world lines look curved and can make a bad homography look internally plausible.
- Camera model selection is part of the first hardware packet. A normal pinhole/radial model may be enough for a cheap webcam, but an iPhone or wide-angle webcam may require OpenCV's fisheye model or another camera model before calibration residuals are meaningful.
- Plumb-line or calibration-harp straightness checks belong in the hardware profile path if residuals curve despite apparently good camera calibration numbers.
- Projector distortion may require a fixed-rig profile or compensation if edge residuals remain high after camera undistortion.
- Projector-side image correction can invalidate the rig profile. Auto-keystone, four-corner correction, digital zoom, display scaling, browser fullscreen size, and hidden projector processing must be disabled or explicitly recorded before interpreting residuals.
- Low-spatial-frequency or circular fiducials such as LFTag/CCTag are fallback marker families if square ArUco/AprilTag/ChArUco patterns fail under projector defocus, low resolution, or glare.
- Photometric black/white preflight did not change synthetic acceptance, but it improved residuals and should be kept as a cheap real-hardware hardening option for glare, shadows, and exposure.
- Projected frame IDs or visible sync markers may be necessary if the camera captures the wrong displayed pattern, partial refresh, rolling bands, or lagged projector output.
- Dense Gray-code or phase-shift structured light is powerful but pattern-heavy. Keep it as a setup/lab fallback, not the first live-table path.
- The hardware spike must measure physical projection error, not only synthetic pixel error.
- The hardware spike must report refusal honestly. A fast refusal plus manual fallback is better than a wrong-confident projector transform.
- Profile invalidation is part of the problem: focus, zoom, projector mode, camera resolution, exposure, or a bumped mount can stale a fixed-rig profile.
- Timing must be measured as an end-to-end table operation: pattern display, camera capture, detection, solve, optional refinement, pass/fail decision, and projected verification.
- A projected pattern can be visible only briefly during setup. The product does not need players to see calibration graphics during play, but it does need the graphics to be detectable under real projector brightness and mat glare.

## Product And Architecture Decisions To Preserve

- Treat the Raspberry Pi/laptop gateway as the owner of active calibration. The DM controller can trigger calibration and review pass/fail status, but the tight camera-projector feedback loop belongs on the local gateway.
- Keep live calibration local-first. Remote storage/auth may later store prepared maps or cached profiles, but the live table should not depend on a remote AI or cloud service to accept a projector-camera transform.
- A cached rig profile is valuable only if the report records the assumptions that make it valid: camera device, camera resolution, lens profile, projector resolution, focus/zoom, projector mode, mount relationship, exposure/white balance policy, and display scaling.
- If the camera source is an iPhone remote camera, the report must record the exact lens/source and whether Center Stage, Desk View, Portrait Mode, Studio Light, stabilization, orientation changes, or any other automatic crop/reframe/effect path was disabled.
- The first durable output should be a small machine-readable rig/session report rather than a polished UI. Future code should be able to answer: what pattern was projected, what frame was captured, which features were detected, which correspondences were used, what transform was accepted, what residuals were held out, and why the solve was accepted or refused.
- Any future mesh or remap output should remain a correction layer on top of the base homography/profile, not an opaque replacement. Persist raw frames, detected features, homography, optional residual mesh, and final warp separately so failures can be debugged.
- The calibration UI should expose manual fallback/nudge controls even if active calibration works. Active calibration seeds or validates the projection; it should not remove the table-speed safety valve.

## Preserved Evidence

Authoritative references:

- [Scout 003](../scout/scout-003-projection-mapping-calibration-techniques.md) records projection-mapping, structured-light, fiducial, lens-undistortion, and mesh-warp evidence.
- [ADR-001](../decisions/adr-001-calibration-architecture.md) records the layered calibration model: reusable camera profile, reusable fixed projector-camera rig profile, and per-session table/mat/grid acquisition.
- `scripts/projected-fiducial-calibration-sim.py` is the runnable synthetic harness.
- `npm run benchmark:active-fiducial-sim` writes artifacts to `test-results/projected-fiducial-calibration-sim/`.
- `docs/evals/registry.yaml` registers `eval:active-fiducial-sim`.
- `package.json` exposes the active simulation command and should remain the entry point for replaying synthetic evidence.

Current synthetic leader:

- Candidate: `projected-perimeter-fiducials-and-interior-circles`.
- Pattern: known-ID ArUco markers around the perimeter plus interior circle targets in one projected frame.
- Parser hardening: detected marker regions are masked before circle extraction, so white blobs inside ArUco markers cannot become circle candidates.
- Expanded check: `npm run benchmark:active-fiducial-sim -- --trials 240 --seed 20260531`.
- Result: `240/240` accepted, `0.071 px` median p95 feature error, `0.086 px` median p95 surface error, `0.427 px` max p95 surface error.
- Synthetic recommendation: both best accuracy and fastest accepted one-frame branch.

Important challengers from the same expanded run:

| Candidate | Frames | Accepted | Median Feature P95 | Median Surface P95 | Notes |
|---|---:|---:|---:|---:|---|
| Perimeter fiducials + interior circles | 1 | 240/240 | 0.071 px | 0.086 px | Current synthetic leader. |
| Target-adapted fiducials + surface circles | 2 | 240/240 | 0.133 px | 0.174 px | Best two-frame fallback. |
| Center fiducials + surface circles | 1 | 240/240 | 0.149 px | 0.198 px | Proved composite idea, weaker layout. |
| Static fiducials + circle refinement | 2 | 240/240 | 0.156 px | 0.372 px | Robust but less accurate across surface. |
| Plain coded fiducials | 1 | 240/240 | 0.193 px | 0.434 px | Robust identity seed, weak surface coverage. |
| ChArUco board | 1 | 239/240 | 0.186 px | 0.385 px | Mature OpenCV fallback. |
| Asymmetric circle grid | 1 | 228/240 | 0.041 px | 0.178 px | Precise when detected, anonymous and less robust. |
| Symmetric circle grid | 1 | 220/240 | 0.053 px | 0.150 px | Precise when detected, weakest acceptance. |

Other preserved findings:

- Known camera undistortion improved raw-vs-truth median p95 from `3.341 px` to `0.102 px` in the expanded lens stress.
- Projector-distortion stress moved from `21.512 px` raw commanded-pixel surface p95, to `7.778 px` with residual mesh, to `0.090 px` with known projector compensation.
- Photometric black/white preflight did not change acceptance because raw marker frames already accepted `240/240`, but improved feature p95 from `0.181 px` to `0.115 px` and surface p95 from `0.420 px` to `0.315 px`.
- Dense Gray-code or phase-shift structured light remains a setup/lab fallback, not the first live-table path.

Line-target challenger notes:

- A line-only active pattern may be easier for local CV than dot detection because Hough/LSD/EDLines/ELSED-style extractors can return long supports directly.
- A one-frame anonymous line grid is not enough. It solves segmentation but not robust correspondence, especially under perspective, crop, missed lines, or repeated spacing.
- The preferred first line test is marker-seeded: project known-ID perimeter markers plus a sparse set of long H/V lines, detect marker IDs for indexing, then solve a point-plus-line or point-seeded line fit.
- The preferred second line test is two-frame: project horizontal lines and vertical lines separately, each with a visible frame ID and indexing cue, then combine the two families after capture.
- A third useful variant is swept indexed lines: project a short sequence where each frame has a small number of line IDs, preserving easy segmentation while avoiding anonymous grid indexing.
- The line challenger should reuse the same artifact packet as circle/fiducial tests: detected line overlays, assigned projector line IDs, inlier/outlier status, residuals, timing, and final physical projection check.
- Success criteria for line targets should be physical residual and timing, not just visually clean extracted lines. The line challenger only beats circle targets if it is faster or more robust under projector blur/glare while preserving correspondence.

Rejected or deferred alternatives from this branch:

- Generic projection-mapping apps are useful UX references for handles, surfaces, and mesh editing, but they do not solve battle-mat grid ownership or the DM workflow.
- One-shot coded structured light is plausible only if sparse fiducials/circles fail; it adds custom decoding complexity.
- Dense structured light should wait until a sparse physical pass proves a single homography plus residual checks cannot meet the table error target.
- Mesh correction should not be promoted from synthetic residuals alone. It becomes relevant only if real hardware shows repeatable local residuals after camera and projector profiles are accounted for.

## First Activation Slice

When this story is no longer deferred, keep the first slice deliberately small:

1. Display the one-frame perimeter fiducial/interior-circle pattern full-screen on the projector output.
2. Capture one frame from the fixed camera and save it before any processing.
3. Detect marker IDs, mask marker regions, detect interior circle centers, assign circles through the marker-seeded homography, and solve the overdetermined projector-to-camera homography.
4. Project a simple verification grid or crosshair through the solved transform.
5. Record timing, feature counts, residuals, a detected-feature overlay, the accepted/refused report, and physical table error.
6. Repeat the same physical packet for one fallback pattern before making any architecture decision.

Do not start by building a polished controller UI. The first useful artifact is a replayable physical calibration packet plus a clear accept/refuse recommendation.

## Scope

Build the smallest physical spike that can:

- project the perimeter-fiducial/interior-circle calibration pattern,
- capture the projected pattern through the fixed camera,
- save raw camera frames, projected pattern images, detected overlays, per-feature correspondences, and a machine-readable JSON report,
- detect marker IDs and circle centers on the gateway,
- mask marker regions before circle detection,
- assign circles from marker-seeded homography,
- solve projector-to-camera homography with robust rejection,
- report detection counts, inlier counts, reprojection error, surface holdout error, and wall-clock timing,
- project a test grid or crosshair pattern using the solved transform,
- record physical alignment error in inches or fractions of a mat square,
- compare the current leader against at least one fallback pattern,
- record which hardware/profile settings were assumed stable and which changes would invalidate the result.

Minimum saved artifact packet:

- source projected pattern image or pattern definition,
- captured raw camera frame,
- detected-feature overlay,
- rejected-feature overlay when useful,
- feature/correspondence JSON with projector coordinates, camera coordinates, feature type, marker ID or line ID, inlier status, and residual,
- accepted homography matrix,
- optional undistortion/remap metadata,
- optional residual mesh/remap metadata,
- physical projection check photo or screenshot,
- timing breakdown for capture, detection, solve, refinement, projection, and total pass/fail time.

## Acceptance Criteria

- A real projector/camera rig runs the active pattern end to end without hand-entered correspondences.
- The report includes projector resolution, camera resolution, camera placement, projector placement, focus/exposure notes, and pattern frame count.
- The report records total calibration time from projecting the first pattern to accepting or refusing a transform.
- The report records marker count, circle count, assigned circle count, inlier count, median/p95 reprojection error, and physical projected-grid error.
- The spike compares the one-frame perimeter composite against at least one of: ChArUco, plain fiducials, asymmetric circles, or target-adapted two-frame refinement.
- The spike records which camera model was tested first and whether a pinhole/radial, fisheye, or other model is required for the selected camera/capture mode.
- The spike records whether phone/webcam capture effects, orientation changes, stabilization, auto-cropping, or remote-camera processing were disabled or made the frame unsuitable for calibration.
- The spike records whether projector auto-keystone, four-corner correction, digital zoom, display scaling, browser fullscreen mismatch, or projector-side processing were disabled or treated as profile invalidators.
- The spike includes a pattern-scale sweep before rejecting a target family: marker size, circle radius, line width, and brightness must be tested at the real throw distance.
- The spike records whether black/white photometric preflight is needed under real glare/shadows.
- The spike records whether camera undistortion and projector compensation are required before residuals are judged.
- The spike records whether decimated global detection plus full-resolution ROI/subpixel refinement can meet timing and accuracy on the gateway hardware.
- The spike records whether a single homography is good enough, or whether residuals point toward fixed-rig projector compensation or a small mesh correction.
- If a seeded solve is close but residuals remain high, the spike records whether ECC/direct image-alignment refinement improves or worsens holdout residuals.
- If a line-target challenger is tested, it must be marker-seeded, encoded, swept, or otherwise unambiguous enough to avoid anonymous repeated-grid indexing failure.
- If projected lines are tested, the spike records whether point-plus-line homography beats circle-center-only homography under projector blur/glare.
- If captured frames are inconsistent, the spike records whether projected frame IDs or sync markers are required before solver tuning continues.
- If homography acceptance is borderline, the spike records whether a-contrario/VSAC-style adequacy gates would refuse the solve instead of returning a wrong-confident transform.
- If controlled setup targets are used, the spike compares at least one of AprilGrid, checkerboard-SB, ChArUco, or the perimeter fiducial/circle pattern instead of treating any one target family as assumed.
- If square fiducials fail on real hardware, the spike records whether low-frequency or circular fiducials are worth a separate fallback story before adopting dense structured light.
- The spike records whether cached camera/rig profiles remain valid after common disturbances: changed resolution, focus, projector display mode, exposure, or a small bump to the mount.
- The spike preserves enough artifacts that a future evaluator can inspect false positives, missed features, and final projected alignment without rerunning the hardware.
- After the geometry check passes, the spike records a separate projected-content visibility check with a representative grid and map colors/textures under room lighting. Geometry can pass while the projection is still too dim, low-contrast, or illegible for the table.
- The final recommendation is explicit: adopt, adapt, defer, or reject active projector-camera calibration for the next physical proof loop.

## Defer Or Stop Criteria

- If a single homography seeded by the best sparse active pattern reaches the physical table-error target quickly and repeatably, defer mesh correction, dense structured light, and projector-distortion compensation.
- If ChArUco or plain fiducials are good enough physically, do not keep chasing the synthetic perimeter-circle leader unless it materially improves setup speed, projection error, or refusal quality.
- If projected markers/circles/lines fail because the hardware cannot expose the projected image cleanly, stop solver tuning and record the hardware/optics blocker before inventing more algorithms.
- If correspondence is the only failure in line or circle targets, prefer adding explicit IDs, marker seeds, frame IDs, or sweep order before moving to a heavier dense structured-light system.
- If calibration cannot survive normal table bumps or focus/exposure changes, treat profile invalidation and quick revalidation as product requirements rather than one-off bugs.

## Non-Goals

- Printed battle-mat grid detection.
- Source map normalization or AI grid evidence.
- Map import, masking, inpainting, fog, or controller polish.
- Remote server/storage/auth.
- Dense Gray-code or phase-shift structured light unless sparse active calibration fails on hardware.
- Replacing manual nudge/scale/rotate fallback controls.
- Choosing final Raspberry Pi, webcam, or projector hardware requirements.
- Making remote AI or remote storage part of live calibration.
- Promoting synthetic-only pixel residuals as proof that the physical table workflow is solved.
- Using active projector-camera calibration as an excuse to pause or discard printed battle-mat grid detection.

## Implementation Plan

- [ ] Re-read Scout 003, ADR-001, and this story before changing the active calibration harness.
- [ ] Replay `npm run benchmark:active-fiducial-sim` and record whether the synthetic leader still holds.
- [ ] Add a projector view or script path that displays the current perimeter-fiducial/interior-circle pattern full screen.
- [ ] Add a camera capture path that saves raw frames and detected overlays.
- [ ] Port the synthetic detection path into a hardware-facing gateway command or prototype endpoint.
- [ ] Run the pattern on laptop-as-gateway hardware first.
- [ ] Compare against at least one fallback pattern.
- [ ] If circle targets fail under blur/glare, add a marker-seeded line-target challenger before escalating to dense structured light.
- [ ] If projected lines are strong, test a point-plus-line homography challenger before treating line evidence as only intersections.
- [ ] If captures look inconsistent, add projected frame IDs or visible sync markers before tuning the solver.
- [ ] Add camera intrinsics/undistortion before interpreting curved residuals as active-pattern failure.
- [ ] Decide whether the camera path needs pinhole/radial, fisheye, or another camera model before comparing pattern residuals.
- [ ] Lock or record the camera capture pipeline, including phone camera lens/source, orientation, stabilization/effects, exposure, and whether Continuity Camera-style crops or effects are disabled.
- [ ] Lock or record the projector/compositor pipeline, including auto-keystone, four-corner correction, digital zoom, display scaling, browser fullscreen size, and projector-side processing.
- [ ] Sweep marker size, circle radius, line width, and pattern brightness at real throw distance before judging target-family failures.
- [ ] Benchmark decimated global detection plus full-resolution ROI/subpixel refinement on the gateway hardware.
- [ ] Try ECC/direct image-alignment refinement only after a feature-seeded homography exists, and reject it if holdout residuals worsen.
- [ ] If camera calibration RMS looks good but physical residuals remain bad, add camera-profile uncertainty/cross-validation before blaming the active pattern.
- [ ] If residuals bend after calibration, add plumb-line or calibration-harp straightness checks before tuning the active pattern.
- [ ] Add black/white preflight only if real lighting or glare creates unstable detection or residuals.
- [ ] Record profile invalidation triggers for focus, zoom, display mode, resolution, exposure, and mount movement.
- [ ] Record timing, residuals, physical alignment error, and failure modes.
- [ ] Decide whether this becomes the durable projector-camera calibration layer.

## Resume Packet

When this story is activated, a future agent should start from this packet:

- Active story to read first: [Story 001](story-001-calibration-projection-spike.md), because it owns the current physical calibration proof loop.
- Architecture to honor: [ADR-001](../decisions/adr-001-calibration-architecture.md), especially the separation between camera profile, fixed rig profile, and per-session scene acquisition.
- Research handoff: [Scout 003](../scout/scout-003-projection-mapping-calibration-techniques.md).
- Synthetic command: `npm run benchmark:active-fiducial-sim`.
- Expanded synthetic command: `npm run benchmark:active-fiducial-sim -- --trials 240 --seed 20260531`.
- Harness file: `scripts/projected-fiducial-calibration-sim.py`.
- Artifact directory: `test-results/projected-fiducial-calibration-sim/`.
- Current first pattern to test physically: perimeter ArUco/fiducials plus interior circle targets in one projected frame.
- First fallback patterns to test physically: projected ChArUco, plain projected fiducials, asymmetric circles, target-adapted two-frame fiducial-plus-circle refinement, AprilGrid/setup-card targets, and checkerboard-SB controlled targets.
- First refinement/fallback algorithms to keep in mind: decimated ROI plus full-resolution subpixel refinement, ECC post-seed alignment, point-plus-line homography, a-contrario/VSAC adequacy gates, and plumb-line distortion checks.
- First physical success metric: useful table alignment in seconds, measured in inches or fractions of a 1-inch mat square.

## Open Questions

- Do projected ArUco markers survive projector blur, keystone, low brightness, and glossy mat glare?
- Are interior circles detected reliably when projected over real mat texture, drawings, minis, hands, or shadows?
- Does the fixed camera need one-time lens intrinsics before active calibration is meaningful?
- Does the capture source need a fisheye or other wide-angle camera model rather than a normal pinhole/radial model?
- Can an iPhone remote camera be made stable enough by disabling automatic effects and fixing lens/orientation/exposure, or is a cheap dedicated webcam easier to profile?
- Does the projector need one-time distortion compensation, or is a per-session homography accurate enough?
- Do projector auto-keystone, digital zoom, display scaling, or browser fullscreen behavior silently change the transform enough to require a hard setup preflight?
- Is the one-frame pattern visually acceptable during setup, or should it be hidden behind a brief calibration flash?
- Can this run fast enough on a Raspberry Pi-class gateway?
- Is the projected map legible and high-contrast under room lighting after geometry passes?
- Does active projector-camera calibration reduce or eliminate the need for manual projector nudge controls, or only seed them?

## Validation Commands

Current synthetic guardrails:

```bash
npm run benchmark:active-fiducial-sim
npm run benchmark:active-fiducial-sim -- --trials 240 --seed 20260531
```

When this story activates, physical validation must replace synthetic-only claims.
