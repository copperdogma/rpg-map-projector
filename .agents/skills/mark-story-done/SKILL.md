---
name: mark-story-done
description: Close a completed RPG Map Projector story after validation
user-invocable: true
---

# /mark-story-done <story-number>

Before marking done:

1. Read the story.
2. Confirm acceptance criteria are satisfied with current evidence.
3. Confirm validation ran or was explicitly skipped by the user.
4. Set status to `Done`.
5. Append closeout evidence.
6. Run `make methodology-compile` and `make methodology-check`.

Never mark a story done just because a follow-up exists.
