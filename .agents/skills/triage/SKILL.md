---
name: triage
description: Recommend the next RPG Map Projector action from Ideal/spec/state facts and lane packets
user-invocable: true
---

# /triage [stories|inbox|health|scout]

Use this to choose one next action that best advances the product Ideal.

Read first:

- `docs/ideal.md`
- `docs/spec.md`
- `docs/methodology/state.yaml`
- `docs/methodology/graph.json`
- `docs/stories.md`
- `docs/inbox.md`
- `docs/scout.md`
- `docs/runbooks/triage.md`

For now, default pressure is Story 001 unless new evidence changes the ranking.
Do not route to remote storage/auth, native iOS, AI cleanup, UI polish, or
additional runtime architecture work before the calibration/projection proof
has physical evidence. The current launcher only owns the Vite workbench port.

If scoped:

- `stories`: delegate to `/triage-stories`
- `inbox`: delegate to `/triage-inbox`
- `health`: delegate to `/triage-health`
- `scout`: inspect `docs/scout.md` and recent scout files, then recommend whether a scout follow-up is warranted

Return the top three credible candidates and one yes-ready recommendation.
