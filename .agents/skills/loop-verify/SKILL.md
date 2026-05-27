---
name: loop-verify
description: Run a bounded verification loop over RPG Map Projector docs, code, or proof artifacts
user-invocable: true
---

# /loop-verify <task>

Use only when the user explicitly asks for a verification loop, parallel review, or strict clean-round proof.

Keep the scope bounded: named files, one story, one diff, or one proof artifact. For docs/ADR alignment, prefer one inspection round plus targeted fixes. For executable behavior, use the strictest relevant checks and stop when remaining findings are minor or explicitly accepted.

Do not use this to prove absent code-dependent lanes in the sparse setup.
