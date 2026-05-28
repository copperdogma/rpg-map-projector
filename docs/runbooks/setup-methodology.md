# Runbook: Setup Methodology

Use `/setup-methodology` when the local methodology package drifts.

## Current Package

- `docs/ideal.md`
- `docs/spec.md`
- `docs/methodology/state.yaml`
- `docs/methodology/graph.json`
- `docs/stories/`
- `docs/stories.md`
- `docs/inbox.md`
- `docs/scout.md`
- `docs/scout/`
- `docs/decisions/`
- `AGENTS.md`
- `.agents/skills/`

## Greenfield Setup Result

This repo has the sparse no-code product package:

- real Ideal/spec from kickoff intake,
- Story 001 for calibration/projection proof,
- state/graph generation,
- scout and ADR framework,
- cheap skill-surface checks,
- allocation-backed local runtime launcher for the Story 001 Vite workbench,
- explicit deferral of UI scout, eval/golden, and codebase scans.

## Validation

Run:

```bash
make methodology-compile
make methodology-check
make skills-sync
make skills-check
make triage-facts-check
git diff --check
```

The current app launcher is intentionally narrow: it owns the Vite workbench
port only. Add gateway/API services later only when the physical proof or a
follow-up architecture story identifies real service boundaries.
