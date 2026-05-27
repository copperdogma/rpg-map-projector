# Runbook: Scout

Use `/scout` when external evidence is needed before choosing a story, ADR, hardware path, library, or architecture direction.

Good scout candidates for this repo:

- projector/camera hardware baselines,
- Raspberry Pi or mini-PC requirements,
- iPhone-as-webcam reliability,
- local web gateway patterns,
- OpenCV calibration examples,
- browser image-editing/canvas libraries,
- optional remote storage/auth architecture,
- optional AI cleanup providers.

## Process

1. Read `docs/ideal.md`, `docs/spec.md`, `docs/methodology/state.yaml`, and the current `docs/scout.md`.
2. Check the latest scout index before assigning a number.
3. Use first-party/current sources for hardware, SDK, auth/storage, browser, framework, or API facts when those facts can drift.
4. Write `docs/scout/scout-NNN-slug.md`.
5. Update `docs/scout.md`.
6. Recommend the follow-up: story, ADR, spec update, inbox note, or reject/defer.

## Output

Every scout should include:

- source/question,
- summary,
- evidence,
- recommendation,
- adoption decision,
- follow-up owner,
- confidence and open questions.
