---
name: create-story
description: Create a scoped RPG Map Projector story and refresh the generated story index
user-invocable: true
---

# /create-story <title>

Create a story only when the work is concrete enough to score against the Ideal/spec.

Story files live under `docs/stories/` and should use canonical names:

```text
story-NNN-short-slug.md
```

Include JSON frontmatter with:

- `title`
- `status`
- `priority`
- `origin`
- `ideal_refs`
- `spec_refs`
- `depends_on`
- `category_refs`
- `compromise_refs`

Then run:

```bash
make methodology-compile
make methodology-check
```
