---
name: finish-and-push
description: Validate, commit, and push RPG Map Projector work when explicitly requested
user-invocable: true
---

# /finish-and-push

Use only when the user explicitly asks to check in, push, or finish-and-push.

1. Inspect current git state and intended scope.
2. Run relevant validation.
3. Stage only intended files.
4. Commit with a terse message.
5. Push to the configured remote.

Never commit or push without explicit user permission.
