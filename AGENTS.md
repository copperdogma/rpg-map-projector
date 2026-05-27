# Agent Instructions

## Project Shape

This repo is a hardware-assisted product prototype for live tabletop RPG play. Treat it primarily as a projection/calibration product, secondarily as a UI and computer-vision app.

## Operating Rules

- Preserve `docs/initial-concept.md` as raw intake. Do not rewrite it into polished project docs.
- Keep `docs/ideal.md` as the product north star and `docs/spec.md` as the durable product spec.
- Use `docs/inbox.md` for loose follow-up ideas before deciding whether they belong in Ideal, spec, assumptions, or a story.
- Favor proof stories that reduce physical feasibility risk over stories that only add scaffolding.
- Do not turn the project into a VTT, campaign manager, token tracker, animated-map system, or map marketplace unless the Ideal/spec are deliberately changed.
- Treat speed at the physical table as a hard product constraint. A slightly imperfect projection in seconds is usually better than a polished result after minutes.
- Keep edits reversible and non-destructive: source images, normalized maps, masks, clean patches, and projection transforms should remain separable.

## Prototype Bias

Until hardware proves otherwise, assume:

- laptop for processing and app hosting,
- HDMI projector for display,
- iPhone as a fixed remote camera mounted to the projector,
- manual calibration fallback before full automation,
- OpenCV-style geometry experiments before polished UI.

## Validation Bias

For early work, validation should be concrete and physical when possible:

- test against a real or printed 1-inch grid,
- capture screenshots or photos of projected calibration output,
- record alignment error in physical squares or inches,
- time the workflow from source map to useful projection.
