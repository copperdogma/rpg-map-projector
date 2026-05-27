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
- explicit deferral of runtime, UI scout, eval/golden, and codebase scans.

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

Do not add app/runtime launchers until there is a real local web gateway. When that exists, use Conductor's local-dev port allocation rather than inventing a port range.
