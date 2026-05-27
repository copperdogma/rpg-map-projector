---
name: init-project
description: Interview-first greenfield project kickoff. Use when the user has a new repo, raw idea capture, docs/initial-concept.md, or an existing unshaped project and wants to start, bootstrap, kick off, or choose which methodology/framework pieces to use. Can be run by pointing a blank-repo agent at this Conductor skill file. Produces a discussed setup plan before any project scaffolding.
user-invocable: true
---

# /init-project [repo-path|new-idea|from-seed|from-existing]

Use this skill to turn a raw project seed into an agreed kickoff plan. It is
not an autonomous scaffolder. The first deliverable is a conversation: what the
project appears to be, what setup options are available, what the agent
recommends, why, and what the user wants to change before setup begins.

This skill often runs from a brand-new target repo that has no local
`AGENTS.md`, skills, stories, or methodology files yet. In that case, keep two
roots separate:

- **Conductor source root**: the repo containing this `SKILL.md`.
- **Target project root**: the new repo being kicked off.

Always read the companion runbook when it is available. Resolve it relative to
this file by replacing `.agents/skills/init-project/SKILL.md` with
`docs/runbooks/new-project-kickoff.md` in the Conductor source root. If the
runbook is unavailable, continue with this skill's embedded workflow.

## Boundaries

- Preserve raw intake such as `docs/initial-concept.md`; do not overwrite it.
- Do not copy another repo wholesale. Use existing projects as references for
  patterns, then adapt only the pieces that fit.
- Do not create or modify target-repo files until the user approves a named
  setup action. A bare `yes` approves only the plan you just stated, not commit,
  push, or cross-repo rollout.
- If the user asks only for advice, stop after the kickoff brief.
- Do not assume the target repo is a git repo or has package/runtime tooling.
- If the target is an existing tracked project, use Conductor's normal
  worktree/checkout guardrails before editing it.

## Interview Workflow

1. **Orient**
   - Verify the exact target repo path and whether it has a git checkout.
   - Read the seed file, usually `docs/initial-concept.md`.
   - Check whether `docs/ideal.md`, `docs/spec.md`, `AGENTS.md`,
     `docs/inbox.md`, or stories already exist.
   - If the seed is missing, ask for the seed path or a short idea capture
     before recommending setup.
2. **Extract**
   - Identify durable product ideals, practical constraints, non-goals, open
     questions, first risks, and likely proof points.
   - Separate raw chronology from durable meaning.
3. **Classify**
   - Pick a primary project shape, with secondary shapes if needed:
     creative/writing, prototype/hardware, web app/product, AI pipeline,
     tooling/library, supervisor/workflow, personal utility, or sparse/no-code.
   - Explain the classification in one or two concrete reasons.
4. **Choose Surfaces**
   - Recommend the minimal useful setup package:
     `docs/ideal.md`, `docs/spec.md`, `docs/inbox.md`, `AGENTS.md`,
     `docs/stories/`, state/graph, setup checklist, eval/golden lane, local
     runtime/ports, UI scout, source-intake, ADRs, scout logs, README, and
     Codex environment setup.
   - Mark each important optional surface as adopt, adapt, defer, or reject.
5. **Discuss**
   - Present the kickoff brief, alternatives, and the first proof story.
   - Ask only the questions needed to resolve material ambiguity.
   - Incorporate the user's corrections before setup.
6. **Set Up After Approval**
   - After explicit approval, create the agreed files and first story.
   - Run `/setup-methodology greenfield` only after real, reviewed
     `docs/ideal.md` and `docs/spec.md` exist and the chosen package warrants
     it.

## Kickoff Brief Shape

```markdown
## Kickoff Brief

### Project Read
- {what this project is trying to become}

### Recommended Shape
- Primary type: {type}
- Why: {evidence from the seed}

### Setup Package
- Adopt: {surfaces}
- Adapt: {surfaces}
- Defer: {surfaces}
- Reject: {surfaces}

### First Proof Story
- {the first story that reduces the largest real risk}

### Questions
- {1-3 material questions, if needed}

### Approval Boundary
- Reply `yes` to proceed with: {specific setup action}
```
