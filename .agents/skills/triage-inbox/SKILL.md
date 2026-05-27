---
name: triage-inbox
description: Route RPG Map Projector inbox items into spec, assumptions, stories, ADRs, or deferral
user-invocable: true
---

# /triage-inbox [scan]

Use `scan` for read-only reporting. Without `scan`, process inbox items only when the user has asked to route them.

For each item in `docs/inbox.md`:

1. Check whether it belongs in `docs/ideal.md`, `docs/spec.md`, `docs/assumptions.md`, a scout, a story, an ADR, or a deferred note.
2. Preserve raw meaning while avoiding duplicate backlog.
3. Keep live-play MVP scope distinct from post-MVP remote server, native iOS, AI cleanup, and hardware sizing work.
4. Run `make methodology-compile` after story/spec/state changes.
