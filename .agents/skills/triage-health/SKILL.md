---
name: triage-health
description: Report sparse health and freshness facts for RPG Map Projector
user-invocable: true
---

# /triage-health [scan]

Read-only health packet.

Run:

```bash
python3 scripts/triage_facts.py
```

Report:

- dirty git state,
- methodology graph status,
- story status,
- ADR/scout counts,
- deferred lanes,
- skill surface status,
- whether any inbox items should be routed.

Do not treat absent runtime, UI scout, evals, or codebase scans as failures before the repo has implementation substrate.
