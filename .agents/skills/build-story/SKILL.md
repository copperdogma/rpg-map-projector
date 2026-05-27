---
name: build-story
description: Execute an RPG Map Projector story with a plan, evidence, and validation
user-invocable: true
---

# /build-story <story-number>

Use this to take a story from plan to validated implementation.

1. Read the story.
2. Read `docs/ideal.md`, `docs/spec.md`, `docs/methodology/state.yaml`, and `docs/methodology/graph.json`.
3. Verify the story still belongs in the current MVP/proof sequence.
4. Write or update a short plan in the story before implementation when scope is non-trivial.
5. Implement only the named story scope.
6. Run the relevant checks and record evidence in the story work log.

For Story 001, prefer empirical calibration/projection evidence over app architecture speculation.
