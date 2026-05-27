---
name: create-adr
description: Create an RPG Map Projector ADR with lightweight research scaffolding for hard-to-reverse product, hardware, or architecture choices
user-invocable: true
---

# /create-adr <number> <short-name> "<title>"

Create ADRs under `docs/decisions/` for decisions that are sticky enough to preserve.

Use ADRs for choices such as:

- local gateway vs remote service boundary,
- native app adoption,
- camera/projector hardware requirements,
- storage/auth model,
- calibration architecture.

## Steps

1. Check `docs/decisions/README.md` and existing `docs/decisions/adr-*` files before assigning a number.
2. Run:

```bash
.agents/skills/create-adr/scripts/start-adr.sh <number> <short-name> "<title>"
```

This creates:

- `docs/decisions/adr-NNN-<short-name>.md`
- `docs/decisions/research/adr-NNN-<short-name>-research-prompt.md`
- `docs/decisions/research/adr-NNN-<short-name>-final-synthesis.md`

3. Fill in the ADR with real context, options, decision, consequences, and references.
4. Update stories/spec/state if the decision changes project direction.
5. Run `make methodology-compile` and `make methodology-check`.

## Guardrails

- Do not create ADRs for ordinary story tasks or low-risk wording changes.
- Never overwrite an existing ADR or research note.
- ADR numbers should stay sequential.
