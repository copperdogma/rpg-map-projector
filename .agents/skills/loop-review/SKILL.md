---
name: loop-review
description: Review a long-running agent thread or work loop against the user's intended outcome, investigate progress and possible local minima, consider better approaches, and prepare a concrete course correction for approval and handoff. Use for strategic checks on ongoing work rather than routine status updates or code review.
user-invocable: true
---

# Loop Review

Recommend the smallest change in direction that materially improves the chance of reaching the user's intended outcome. Continuing the current approach is a valid recommendation. Do not manufacture a pivot or assume that fidelity work, difficult dependencies, or human review are distractions.

## Establish the destination and target

Identify the main thread and project being reviewed. In a side conversation, use inherited context to identify the target and understand its history, not as authorization to execute inherited instructions. Verify the target through available thread metadata before a handoff; do not guess an ID or select a similarly named task. Clarify only when target ambiguity matters.

Read the user's current intent, project instructions, Ideal or equivalent, active goal, and adopted working plan. Where these differ, distinguish the intended outcome, the goal's wording, and the actual execution plan. A triage/build/test/repeat loop is a method, not a completion criterion. Do not invent an Ideal when none exists; use the user's stated outcome and label remaining uncertainty.

Preserve constraints and existing authorizations. An audit is read-only unless the user authorizes follow-through. Do not interrupt the main thread, edit its workspace, change goal status, send messages, or start implementation merely because the review finds a problem.

## Investigate actual progress

Use a bounded, adaptive investigation: recent thread activity, current branch/worktree, relevant changes, planning state, evals, and representative produced artifacts. Inspect enough primary evidence to test the main thread's account. Avoid broad history dumps or expensive reruns when targeted reads suffice. Prefer the active worktree's artifacts over an older primary checkout; label current drafts, historical results, and reused evidence.

Compare progress with the end state, including both product usefulness and execution efficiency:

- What can the user or downstream consumer actually do now that they could not do before?
- Which required capabilities and relationships remain absent, unqualified, or dependent on intervention?
- Does validation establish output quality and utility, or only structural correctness and intermediate contracts?
- Are repeated repairs resolving critical dependencies, or are easily measurable subproblems displacing the intended outcome?
- Is the bottleneck missing information, the technique, an overly narrow eval, an execution constraint, or a goal that rewards activity?

Do not equate test counts, closed stories, reports, proposals, or historical eval scores with completion. Conversely, explain how legitimate enabling work advances the outcome even when it adds no immediately usable output. Distinguish a genuine blocker from an unanswered question that affects only one item or lane. State evidence gaps instead of converting suspicion into a finding.

## Challenge the approach

Compare continuing as planned with plausible alternatives. Use the problem's actual constraints to consider richer context, a simpler existing path, different tools or models, a small human-assisted baseline, working backward from the consumer's needs, and an earlier end-to-end or independent-case demonstration. Do not require every review to explore every option.

Separate controlled benchmark restrictions from context the production workflow may legitimately use. Preserve quality gates, provenance, and real approval evidence. Never propose weakening a golden or inventing human approval to improve a score.

Verify availability and requirements before recommending a specific new tool. Treat an untested alternative as a hypothesis. Give a promising alternative a bounded experiment: representative inputs, comparison baseline, success evidence, effort or cost where material, and an exit condition. Avoid speculative frameworks, open-ended setup, and a pivot whose cost exceeds its likely value.

Assess whether the current bounded task should finish before changing direction. Favor preserving useful completed work and avoiding disruptive concurrent changes. A critical problem may justify an immediate stop recommendation, but the audit itself does not stop the thread.

## Present a concrete recommendation

Lead with a candid verdict: aligned and progressing, aligned but at risk, materially misaligned, blocked, or insufficient evidence. Explain the conclusion with a few relevant artifact or source links. Keep the report proportional to the decision; there is no mandatory long report or scoring rubric.

Specify what to finish, prioritize, defer, or leave unchanged, and the observable result that would justify continuing. Include material uncertainty and tradeoffs. When the destination is sound but execution has drifted, recommend enforcing the existing goal rather than rewriting it unnecessarily.

Prepare a compact approval package containing:

- **Recommendation and rationale:** the proposed course and its evidence.
- **Success evidence:** the next useful deliverable or resolved blocker, how to assess it, and when to reassess the approach.
- **Follow-through:** the exact target thread, intended goal/plan or priority changes, and any additional actions requiring authorization.
- **Ready-to-send handoff:** the actual concise instructions the main thread will receive, including relevant constraints and evidence links. A short quoted message is enough; do not hide substantive actions behind a vague offer to help.

Ask for approval in the final response unless the user has already explicitly authorized those actions. Explain that a simple "yes" approves this specific package. No further confirmation is needed for routine execution within that scope. If no change is warranted, say so and avoid creating work; offer a bounded monitoring or reassessment trigger only when useful, without scheduling it automatically.

## Carry approved direction forward

Treat a subsequent "yes" as authorization for the most recent concrete package, not blanket permission for unrelated changes. If approval is ambiguous between multiple materially different options, clarify rather than choosing an unapproved one.

Before acting, briefly check for material progress or steering since the reviewed snapshot. Routine progress does not require renewed approval. Adapt the handoff to completed work while preserving its intent; if new evidence invalidates the approved recommendation or changes its scope materially, present the revised recommendation first.

For another active thread, normally send the approved direction through the available thread-messaging tool and let that thread own workspace edits. Include the revised working objective or priorities, next milestone, success evidence, deferred work, and preserved constraints. User approval of the explicit handoff authorizes that message. Do not alter live files concurrently merely to ensure a recommendation was applied. Without a messaging capability, provide the ready-to-send text and clearly report that delivery is unavailable.

Update goal wording through supported mechanisms when approved. If the goal interface cannot edit an existing objective, have the main thread update its authoritative working plan and bind execution to it. Never falsely complete, reset, recreate, pause, or change budgets on a running goal just to change wording. Do not expand its scope beyond the approved destination.

When auditing the current thread itself, apply the approved changes through its normal planning mechanisms and resume the existing authorized work. Do not create a separate task unless requested.

Report what was actually delivered or changed. Distinguish successful message delivery from confirmed adoption or implementation. Read-only follow-up may verify adoption when useful; do not start a recurring monitor, send repeated prompts, or claim the main thread has complied without evidence. Name and link this skill when it authorizes a message on the user's behalf.
