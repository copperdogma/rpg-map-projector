---
name: scout
description: Investigate an external source, hardware option, library, or architecture pattern for RPG Map Projector
user-invocable: true
---

# /scout <source-or-question>

Use this when the next product or implementation choice depends on external evidence.

## Source Handling

Before generic web reading, choose the narrowest honest retrieval path:

- hardware, SDK, browser, auth/storage, framework, or API facts: prefer current first-party docs, specs, changelogs, official repositories, manufacturer pages, or datasheets;
- OpenAI/API/model facts: use official OpenAI docs or first-party provider docs;
- YouTube source: use YouTube transcript tooling when available;
- X/Twitter source: use Twitter/X tooling when available;
- local project notes: read the named local files directly.

## Steps

1. Read `docs/ideal.md`, `docs/spec.md`, `docs/methodology/state.yaml`, and `docs/scout.md`.
2. Check existing scout numbers before assigning a new one.
3. Investigate the source or question enough to make a decision.
4. Compare evidence against live-play speed, local-first projection, gateway responsibilities, and post-MVP remote storage/auth direction.
5. Choose one decision label: `Adopt`, `Adapt`, `Defer`, `Reject`, or `Spike`.
6. Write `docs/scout/scout-NNN-slug.md` using the template.
7. Update `docs/scout.md`.
8. Recommend the follow-up owner: story, ADR, spec/state update, inbox note, or no action.

## Guardrails

- Do not treat interesting as worth doing.
- Do not use stale commentary for current hardware/API/provider facts when official sources are easy to check.
- Do not turn remote server, native iOS, or AI cleanup ideas into MVP work unless Story 001 evidence changes the priority.
- If the scout reveals a hard-to-reverse choice, recommend an ADR before implementation.
