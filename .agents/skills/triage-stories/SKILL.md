---
name: triage-stories
description: Evaluate RPG Map Projector stories and recommend the best next story action
user-invocable: true
---

# /triage-stories [story-number]

Read-only story triage.

1. Read `docs/methodology/graph.json` and `docs/stories.md`.
2. Read candidate story files under `docs/stories/`.
3. Score by product leverage, current substrate, proof value, and readiness.
4. Recommend one action.

Prefer physical calibration/projection proof before app polish, remote storage, AI cleanup, or hardware shopping. If the story cannot be scoped without external evidence, recommend `/scout` or an ADR before implementation.
