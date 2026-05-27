---
name: validate
description: Validate RPG Map Projector work against intent, story requirements, and local checks
user-invocable: true
---

# /validate [story-number]

Validate with fresh current-pass evidence.

1. Inspect `git status --short`, `git diff --stat`, and relevant diffs.
2. If a story is in scope, read the story and acceptance criteria.
3. Check changes against `docs/ideal.md` and `docs/spec.md`.
4. Run relevant checks:

```bash
make methodology-check
make skills-check
make triage-facts-check
git diff --check
```

When implementation code exists, add repo-specific tests before claiming completion.
