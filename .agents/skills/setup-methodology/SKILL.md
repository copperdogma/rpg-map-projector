---
name: setup-methodology
description: Canonical installer/normalizer for the full Ideal-first methodology package after Ideal/spec intake exists, including upgraded triage, core story-loop, and loop-verify bootstrap
user-invocable: true
---

# /setup-methodology [greenfield|retrofit|adr-021-migration|refresh]

> Alignment check: Before choosing an approach, verify it aligns with
> `docs/ideal.md`, `docs/methodology/state.yaml`,
> `docs/methodology/graph.json`, and relevant decision records in
> `docs/decisions/`. If this work touches a known compromise in `docs/spec.md`,
> respect its limitation type and evolution path. If none apply, say so
> explicitly.

Use this skill as the **canonical full-package setup entrypoint** for the
methodology package. It assumes project-specific `docs/ideal.md` and
`docs/spec.md` already exist from `/init-project` or equivalent source-backed
intake. `/init-project` is interview-first: it should discuss project shape,
setup options, and first proof stories with the user before creating files.
This skill replaces the old phased setup surface with one integrated package
installer/normalizer.

`/setup-methodology` does not discover a blank project's idea. For a greenfield
folder with no real Ideal/spec, stop and route to `/init-project new-idea`;
do not treat that route as approval to scaffold without the kickoff interview.

## What This Skill Owns

- `docs/ideal.md` / `docs/spec.md` / `docs/methodology/state.yaml` / `docs/methodology/graph.json` alignment after Ideal/spec intake
- `docs/setup-checklist.md` working copy generation from the bundled template
- eval harness bootstrap, day-zero golden workspace bootstrap, and root eval
  ladder setup where the repo owns product evidence
- story/decomposition bootstrap
- core story-loop bootstrap: `/create-story`, `/build-story`, and `/validate`
  guidance for optional sidecar evidence, plan-gated delegation, parallel
  validation, and `/loop-verify` escalation
- optional `/ideation` helper bootstrap for high-ambiguity Ideal/spec drafting,
  ADR option expansion, story-boundary shaping, and story-plan alternatives
  where option quality is the blocker
- optional `/triage-adr` helper bootstrap for existing ADRs whose remaining
  decisions, maturity, or next route are unclear
- fresh upstream documentation as an active dependency for drift-prone
  providers, SDKs, model/provider slugs, browser/tooling plugins,
  UI/component libraries, auth/payment/storage providers, and framework APIs
- upgraded triage bootstrap: `/triage`, lane-packet leaf skills,
  `/triage-health`, sparse-safe triage facts, and skill-surface sync
- codebase-improvement lane setup when the repo has enough code for a scan:
  report-first discovery, optional algorithmic-complexity detector guidance,
  optional periodic semantic-review detector guidance, local proof
  requirements, and guarded story/auto-fix routing
- upgraded verification bootstrap: `/loop-verify` mode selection, budgeted
  defaults, docs/ADR inspect-only behavior, and strict clean-round escalation
- local runtime allocation bootstrap for repos that expose a local web/API
  surface: Conductor-owned port allocation, repo-local launch/status/stop
  scripts, strict binding, health identity, and README/Codex action guidance
- Codex worktree dependency bootstrap for repos with validation or runtime
  tools: repo-owned setup command, `.codex/environments/environment.toml`
  wiring, and no-source-mutation guardrails
- optional recurring methodology lanes already encoded in the package, such as
  `architecture_audits` / `/triage-architecture` and `ui_scout` /
  `docs/ui-scout*`
- `AGENTS.md` methodology wiring and state/graph-first operating rules
- canonical `.agents/skills` sync via `scripts/sync-agent-skills.sh`, with
  provider-specific command aliases only when a repo explicitly keeps them
- repo-specific package variants, including Conductor's supervisor routing,
  scouting, and alignment surfaces when the repo identity is Conductor

Use the bundled checklist template at
`.agents/skills/setup-methodology/templates/setup-checklist.md` and the mode
reference at `.agents/skills/setup-methodology/references/modes.md` when that
bundle exists. If a repo intentionally carries a lean local setup package
without those files, refresh `docs/setup-checklist.md` directly and record the
local variant in the setup summary.

## Modes

### `greenfield`

For a new project after `/init-project new-idea` or equivalent intake has
produced reviewed `docs/ideal.md` and v0 `docs/spec.md`. Install and normalize
the full methodology package around those authored truths: state/graph,
checklist, eval + golden bootstrap, story bootstrap, and public skill surface.

### `retrofit`

For an existing project that needs the full methodology package applied or
reapplied. Read the repo thoroughly, classify what already exists, preserve
provenance, and bring the project onto the canonical package. If the project
lacks a real Ideal/spec, route through `/init-project from-existing` first to
reconstruct them from code/docs and user conversation.

### `adr-021-migration`

For repos that already use Ideal-first but still need the ADR-021 structure:
dual ideal, category-aligned spec/state structure, execution constraints, and
state/graph-centered planning.

### `refresh`

For repos that already have the package but need it re-synced: update AGENTS,
runbook, checklist structure, eval/golden references, and public-surface docs
without redoing the whole bootstrap conversation.

## Repo Package Variants

Keep this setup skill text byte-identical across Conductor and the tracked
product repos. Apply the package according to repo identity rather than
silently forking the setup contract.

- **Product repos** use the full product methodology package: Ideal/spec,
  state/graph, eval/golden bootstrap or explicit deferral, story loop, triage,
  optional recurring lanes, AGENTS, canonical skills, and compatibility links.
- **Conductor** uses the supervisor package: `projects.yaml`, `inbox.md`,
  `docs/scout.md`, `docs/scout/`, `docs/align-projects.md`,
  `docs/alignments/`, and supervisor skills such as `/align-projects`,
  `/scout`, and `/triage-stories` are first-class setup surfaces. Do not import
  product-only eval/golden/UI lanes into Conductor unless its Ideal/spec/state
  explicitly add them; mark them absent or deferred instead. Still install or
  refresh the shared triage, core story-loop, and `/loop-verify` guidance so
  Conductor follows the same practical loop: triage, create story, build,
  validate, close out.

## Working Rules

1. **Ideal/spec preflight is mandatory.** Before installing package surfaces,
   verify `docs/ideal.md` and `docs/spec.md` exist and are project-specific.
   They may be v0, but they must be real authored artifacts. If either is
   missing, generic, only a placeholder, or not yet reviewed for cohesion
   against raw intake, stop and route to `/init-project`; do not fabricate them
   from the setup template or skip the user-facing kickoff discussion.
2. **Create or refresh the checklist first after preflight.** Copy the bundled
   template to `docs/setup-checklist.md` if the template exists and the working
   checklist is missing or still an older one-off format. If the repo has no
   bundled template by design, refresh the local checklist directly. Work from
   that file and check items off as the run proceeds.
3. **State/graph-first operating rule:** planning and triage start from
   `docs/methodology/state.yaml` and `docs/methodology/graph.json`.
   Implementation starts from the active story, but must read the relevant
   `spec:N` sections plus the matching state/graph slice first.
4. **Treat goldens and evals as baseline setup when the repo owns product
   evidence.** Day-zero product setup is incomplete
   until the repo has the golden workspace, the eval harness/story, and a root
   Ideal eval or explicit deferral. For AI-capability work, preserve the
   initial decomposition ladder: root eval, known parent failures, child evals,
   and the implementation stories that exist because those evals fail. For
   Conductor or other non-product supervisor packages, preserve local
   supervisor evidence surfaces instead and mark product-only evidence lanes
   absent or deferred. When setup or story work identifies a new AI
   compromise, attach or create the owning compromise/deletion eval, or record
   an explicit deferral with the trigger that would make the eval worth
   creating later.
5. **Choose the eval substrate by proof shape.** Default to PromptFoo when the
   proof is prompt/model comparison, rubric or judge scoring, or repeated
   output-quality checks over a stable case set. Prefer a custom runner, script,
   browser check, artifact inspection, golden verifier, or runtime benchmark
   when the proof is structural behavior, deterministic pipeline truth,
   browser/UI behavior, visual or media artifacts, or instrumentation that
   PromptFoo cannot represent honestly.
6. **Treat fresh upstream docs as an active dependency for drift-prone external
   surfaces.** When setup, story, triage, scout, or validation work touches an
   API provider, SDK, model/provider slug, browser/tooling plugin,
   UI/component library, auth/payment/storage provider, or framework API, check
   current first-party docs, release notes, changelogs, official repositories,
   or a source-specific docs connector before changing code, defaults, prompts,
   SDK calls, config, or methodology advice. This is not ritual browsing:
   stable repo-local behavior can use local docs/tests first when no external
   interface fact is at issue. Upstream docs answer "what is true now";
   repo-local Ideal/spec/compromise/eval surfaces answer "what is good and
   safe for this product."
7. **Prefer outcome-first prompt contracts over inherited process stacks.**
   Prompts and skills should state the desired outcome, constraints, available
   evidence, final answer shape, and real local guardrails. Keep detailed
   process where it protects against known failures such as dirty checkouts,
   destructive git, exact-path mistakes, UI/browser proof gaps, eval
   completeness, provider freshness, or data-loss risk. Soften or remove
   generic process text that only compensates for older model behavior and
   narrows the model without improving proof.
8. **Keep recurring work separate.** The bootstrap skill installs the package
   and preserves optional recurring lanes that are already part of it. Ongoing
   product work uses `/create-eval`, `/improve-eval`, `/align`,
   `/triage-architecture`, the local `ui-scout` lane when `state.ui_scout`
   exists, story/build skills, and normal ADR/story workflows. Conductor
   supervisor work uses `/align-projects`, `/scout`, `/triage-stories`, the
   core story loop, and normal ADR/story workflows.
9. **Keep codebase-improvement report-first.** When a repo has enough code for
   `/codebase-improvement-scout`, algorithmic complexity scanning is one
   optional deterministic detector category, not a standalone optimizer. It may
   look for nested scans, membership/search inside loops, sort-in-loop behavior,
   render-derived collection work, N+1-shaped IO/query/API loops, and repeated
   expensive derivations. Treat these as leads until local code reads confirm
   the data shape, hot path, expected complexity before and after, risk level,
   and the tests, benchmarks, profiler/browser evidence, or manual measurements
   needed. Do not require remote npm helpers such as `npx
   codex-complexity-optimizer` in normal workflows; use instruction-level
   guidance first, and only add reviewed local helpers if repeated scans prove
   they are worth maintaining.
   Periodic AI semantic review, such as a bounded Clawpatch run, is another
   optional detector category for stale, high-churn, thinly-tested, pre-release,
   or pre-cleanup code areas. Keep it isolated, version-pinned, report-only,
   and manually verified. Do not put it in CI, normal `/validate`, or every
   story closeout, and do not run tool-managed fix paths during scout-mode use.
10. **Core story-loop setup is part of refresh.** Install or refresh
   `/create-story`, `/build-story`, `/validate`, and the optional `/ideation`
   helper with the accepted core-loop guidance: the main thread owns
   Ideal/spec judgment, story boundaries, build plans, option selection, and
   final validation disposition; subagents gather bounded sidecar evidence,
   divergent option packets, or disjoint non-blocking work only when that
   reduces risk; sequential fallback is explicit; and `/loop-verify` escalation
   is reserved for repeated material review/fix rounds. Do not make subagents,
   `/ideation`, or `/loop-verify` mandatory for ordinary setup, no-code repos,
   routine story creation, or small validation passes.
11. **Canonical public surface only.** AGENTS/docs should advertise
   `/init-project` for greenfield idea intake and `/setup-methodology` for
   full package setup. Do not reintroduce the old phased setup skills.
12. **No-code repos get a sparse package, not a long forensic loop.** When a
   repo has little or no code, install the methodology surfaces quickly around
   the authored Ideal/spec, mark unavailable lanes as absent or deferred, and
   avoid asking agents to infer runtime truth that cannot exist yet.
13. **Shared skill surfaces should be copied exactly.** When this setup skill or
   the shared triage/core story-loop/loop-verify package changes, upgrade one
   source copy and perform a local propagation sweep. Cross-repo propagation is
   separate repo-local adoption work: use dedicated target-repo worktrees or an
   explicit safe execution path, copy exact shared files there, and run that
   repo's skill-surface checks before claiming the target repo is updated. Do
   not independently rewrite the same skill in each repo.
13. **Local runtime setup uses Conductor allocation.** When a repo has a local
    browser UI, API, internal authoring server, catalog review server, or other
    human/AI runtime, add a repo-local launcher that reads Conductor's
    `local-dev-ports.json` allocation instead of inventing ports. Primary
    checkouts use the canonical primary ports. Worktrees persist a stable slot
    by absolute path in `~/.codex/local-dev-ports.json` and derive ports only
    inside the repo's assigned range. Launchers must use strict binding, report
    status with project/check-out/slot/port/PID/health details, reuse healthy
    same-checkout services, refuse ports owned by another checkout unless
    explicitly forced, and stop only same-checkout processes by default. Repos
    with no local runtime should record reserved ranges in README/setup docs
    and defer the launcher until a real runtime exists.
14. **Codex worktree setup is explicit dependency bootstrap, not runtime
    launch.** When a repo needs local dependencies before validation or Codex
    Run actions work, add a repo-owned setup command such as
    `scripts/codex-setup` and point `.codex/environments/environment.toml`
    `[setup].script` at that command. Keep package-manager logic in the repo
    command, not in TOML. Setup commands must be idempotent,
    lockfile-respecting, and limited to restoring ignored dependency/tool
    artifacts such as `.venv`, `.runtime`, or `node_modules`. They must not
    rewrite source files, lockfiles, generated methodology outputs, user data,
    or start local servers. After adding an environment file, confirm it is
    visible to git; if `.codex/` is ignored, add a narrow unignore rule for the
    environment TOML or record that the wiring is intentionally local-only.
    Repos without local dependency needs may use a cheap check-only setup hook
    or explicitly defer the hook.

## Greenfield / No-Code Fast Path

For a repo with no meaningful code yet, the goal is to install a useful package
without spending many rounds proving absent evidence. Do this:

1. Verify `/init-project` or equivalent intake produced real `docs/ideal.md`
   and `docs/spec.md`. If not, stop and route back to intake.
2. Create the smallest coherent methodology state/graph that reflects the
   authored Ideal/spec. Do not invent implementation history.
3. Install the shared skill package exactly:
   - `/triage` with main-thread Ideal/spec synthesis, top-three recommendations,
     and one final yes-ready recommendation
   - `/create-story` with optional sidecar evidence for non-trivial story
     scoping while the main thread owns the final story boundary
   - `/ideation` as an optional helper for high-ambiguity Ideal/spec drafting,
     ADR options, story boundaries, and build-plan alternatives where option
     quality is the blocker, with final judgment left to the caller
   - `/triage-adr` as an optional helper for existing ADRs whose remaining
     human decisions, technical recommendations, evidence gaps, or alignment
     route are unclear
   - `/build-story` with delegation only after the plan gate, only for bounded
     non-blocking work with disjoint ownership
   - `/validate` with optional parallel validation packets and escalation to
     `/loop-verify` only when a complete material clean round matters
   - triage leaf skills in packet mode where their lanes are present
   - `/triage-health` for sparse health/freshness packets
   - `/loop-verify` with budgeted default mode, docs/ADR inspect-only mode,
     strict clean-round mode for approved objective proof, and
     material-vs-minor stop rules
4. Add a sparse-safe triage fact collector when the repo has enough tooling to
   support one. It should report absent/deferred/empty statuses directly rather
   than treating missing reports, missing codebase scans, missing UI scouts, or
   missing eval attempts as broken files.
5. Mark optional lanes honestly:
   - `architecture_audits`: deferred until there is architecture to audit
   - `ui_scout`: absent or deferred until there is a real UI surface
   - eval/golden lanes: present only when there is an actual initial eval or an
     explicit deferral with a trigger
   - codebase-improvement: absent until there is enough code for a scan
6. Run cheap validation only: skill-surface check, methodology compile/check,
   direct fact JSON parse if a fact script exists, and whitespace/diff checks.
   Do not run heavy evals, browser scouts, provider calls, or repeated
   subagent verification just because evidence is absent by design.
7. Before the first `/loop-verify`, run a local propagation sweep for shared
   semantics across the main triage skill, core story-loop skills, leaves,
   health runbook, fact script, tests, and skill-surface checks. This prevents
   Echo-style long loops where the same fact meaning is rediscovered one
   adjacent surface at a time.
8. If the repo already exposes, or this setup creates, a local browser/API
   runtime, install the local runtime launcher pattern. Use the Conductor
   allocation file for primary ports, worktree ranges, and service offsets;
   document the command in README and Codex actions. If no runtime exists,
   document the reserved range and defer launcher implementation.
9. If the repo needs local dependencies for validation or runtime commands,
   install a Codex worktree setup hook. Point
   `.codex/environments/environment.toml` at the repo-owned setup command and
   keep Run actions separate from setup so dependency hydration never silently
   starts a server.

## Steps

1. **Determine mode from repo reality** — new repo, retrofit, ADR-021 migration,
   or refresh. If the user supplied a mode, verify it matches what the repo
   actually looks like.

2. **Run the Ideal/spec preflight**:
   - Confirm `docs/ideal.md` exists and is not a blank/template placeholder
   - Confirm `docs/spec.md` exists and has real project-specific compromise or
     constraint content
   - For greenfield, confirm the artifacts came from `/init-project` or
     equivalent idea intake
   - Confirm the Ideal/spec were reviewed against raw intake for coverage,
     contradictions, duplicate ideas, and late-arriving Ideal material
   - If this fails, stop and tell the user to run `/init-project new-idea` or
     `/init-project from-existing`

3. **Read the canonical references**:
   - `docs/runbooks/setup-methodology.md`
   - `docs/methodology-ideal-spec-compromise.md`
   - relevant ADRs in `docs/decisions/`
   - `AGENTS.md`
   - existing setup/eval/golden/story docs if present

4. **Create or refresh `docs/setup-checklist.md`** from the bundled template
   when the template exists; otherwise refresh the repo's local checklist
   directly. Replace placeholders and check items off as work is completed.
   Never treat the checklist as optional.

5. **Install or refresh the methodology package around the authored Ideal/spec**:
   - `docs/ideal.md` — product + execution ideal, preserved/refined from intake
   - `docs/spec.md` — category-aligned constraint source, preserved/refined from intake
   - `docs/methodology/state.yaml` — central operational state
   - `docs/methodology/graph.json` — compiled methodology joins
   - `docs/stories.md` — generated story view
   - `docs/runbooks/setup-methodology.md` — prose front door
   - core story-loop skill surfaces — `/create-story`, `/build-story`, and
     `/validate` with accepted sidecar/delegation/parallel-validation guardrails
   - optional recurring lane docs/routing such as `docs/ui-scout.md`, its
     companion runbook, and AGENTS/triage references when `state.ui_scout`
     exists
   - `AGENTS.md` — canonical public surface and operating rules
   - for Conductor, preserve supervisor surfaces instead of product-only lanes:
     `projects.yaml`, `inbox.md`, `docs/scout.md`, `docs/scout/`,
     `docs/align-projects.md`, and `docs/alignments/`
   - for repos with a local runtime, preserve or install the Conductor-backed
     local launcher surface: allocation-file lookup, stable worktree slot
     derivation, strict ports, health identity, status/start/stop commands,
     README guidance, and Codex action wiring
   - for repos with local validation or runtime dependencies, preserve or
     install a Codex worktree setup hook that restores ignored dependency
     artifacts without mutating source, lockfiles, generated methodology
     outputs, or user data

6. **Bootstrap baseline evidence infrastructure**:
   - For Conductor or another non-product supervisor package, preserve local
     supervisor evidence surfaces and explicitly defer product-only golden/eval
     lanes unless the repo state adds them.
   - For product evidence lanes, continue with the golden/eval checks below.
   - Ensure the golden workspace exists and matches project schemas
   - Ensure the root Ideal eval/golden exists or is explicitly deferred with a
     reason and a next trigger
   - Ensure any day-zero child evals record their parent eval and measured
     failure mode
   - Ensure each new AI compromise has an owning compromise/deletion eval, or
     an explicit deferral reason plus the trigger that would make the eval
     worth creating later
   - Choose PromptFoo only when it fits the proof shape: prompt/model
     comparison, rubric or judge scoring, or repeated output-quality checks over
     a stable case set. Use custom runners, scripts, browser checks, artifact
     inspection, golden verifiers, or runtime benchmarks when those prove the
     actual behavior more honestly.
   - Ensure the eval package exists and is wired together: `docs/evals/README.md`,
     `docs/evals/registry.yaml`, `docs/evals/attempt-template.md`,
     `docs/runbooks/promptfoo.md` when promptfoo applies, and the linked
     `tests/fixtures/golden/` workspace or repo-equivalent locations
   - Ensure day-to-day eval creation and improvement paths are documented and
     installed (`/create-eval`, `/improve-eval`)

7. **Bootstrap story/planning infrastructure**:
   - Ensure state/graph-backed story decomposition exists
   - Ensure the story framework points back to methodology state/graph + spec,
     not to a stale feature-map or legacy dashboard model
   - Ensure `/create-story` preserves optional sidecar evidence only for
     non-trivial scoping and keeps the main thread responsible for the final
     story boundary
   - Ensure `/build-story` preserves the human plan gate and allows delegation
     only after that gate for bounded, disjoint, non-blocking work
   - Ensure `/ideation` is installed as an optional helper for high-ambiguity
     Ideal/spec drafting, ADR options, story boundaries, and build-plan
     alternatives where option quality is the blocker
   - Ensure `/triage-adr` is installed as an optional helper for existing ADRs
     that need a decision inventory, maturity read, and next-route
     recommendation
   - Ensure `/validate` preserves main-thread final disposition while allowing
     optional parallel validation packets and `/loop-verify` escalation for
     material repeated review/fix rounds
   - Ensure `/build-story` and `/validate` both require current upstream docs
     evidence, or an explicit local-only rationale, when a story or diff
     touches drift-prone providers, SDKs, browser/tooling plugins,
     UI/component libraries, model/provider slugs, or framework APIs

8. **Install the upgraded triage, core story-loop, and verification surface**:
   - Install or refresh `/triage` as the orchestration skill: Ideal/spec first,
     main-thread facts, neutral lane packets, top three recommendations, and
     one final yes-ready recommendation.
   - Install or refresh `/create-story` so subagents are optional sidecars for
     non-trivial evidence gathering only. The main thread decides whether a new
     story is warranted, sets story boundaries, and owns the final artifact.
   - Install or refresh `/build-story` so delegation starts only after the
     required plan/human gate and only for bounded sidecar exploration,
     disjoint implementation slices, tests, or review work. The main thread
     owns the plan, scope coherence, and final handoff.
   - Install or refresh `/ideation` as an optional helper for high-ambiguity
     Ideal/spec drafting, ADR option expansion, story-boundary shaping, and
     build-plan alternatives. Caller skills keep final decision authority.
   - Install or refresh `/triage-adr` as an optional helper for existing ADRs
     whose decision inventory, evidence gaps, or align/story route are unclear.
     ADRs and repo-local normative surfaces keep final decision authority.
   - Install or refresh `/validate` so parallel validation packets can inspect
     changed files, acceptance criteria, checks, and architecture/intent fit
     when the diff warrants it. The main thread synthesizes the report and
     final grade/disposition.
   - Install or refresh packet-mode triage leaves. In full `/triage`, leaves
     return candidates and stop conditions; they do not emit lane-local final
     recommendations, kickoff phrasing, or yes-ready handoffs.
   - Install or refresh `/triage-health` only as a sparse health/freshness
     packet lane. It reports architecture, UI, eval, codebase, methodology,
     skill-surface, dependency, or provider risks without running deeper audits
     by default.
   - Install or refresh a sparse-safe triage fact collector when repo tooling
     exists. It must be cheap, read-only, deterministic, and parseable through
     the direct script command.
   - Install or refresh `/loop-verify` with mode and materiality guidance:
     ordinary loops use a budgeted default, docs/ADR alignment uses find-only
     workers plus main-agent fixes, strict clean-round loops are reserved for
     explicit or objective contract-critical proof, material executable or
     contract fixes reset strict loops, and minor typo/formatting/non-contract
     wording fixes only need targeted checks.
   - Install or refresh source-routing guidance so provider/component/model
     work checks current official upstream docs first when those facts are
     likely to drift, then ties any adoption back to local Ideal/spec/evals.

9. **Run the shared-surface propagation sweep**:
   - Check that setup, triage, core story-loop skills, triage leaves,
     triage-health, loop-verify, runbooks, fact script/tests, and skill-surface
     checks agree on the same terms.
   - For no-code repos, confirm absent/deferred lanes are explicit and do not
     create fake triage pressure.
   - Confirm direct fact commands are separate from convenience package scripts
     so package-manager banners cannot corrupt JSON proof.
   - Confirm skill-surface facts distinguish canonical `.agents/skills`,
     compatibility links, optional command aliases, and drift; UI/eval facts
     distinguish empty paths, deferred evidence, and broken pointers.
   - Confirm local runtime docs and launchers agree on Conductor-owned port
     allocation. Runtime-heavy repos should expose launch/status/stop commands;
     headless or no-code repos should explicitly defer launchers while keeping
     their reserved ranges visible.

10. **Normalize the public skill surface**:
   - `init-project` is the greenfield idea-intake seed skill
   - `setup-methodology` is the canonical full-package setup entrypoint
   - old phased setup skills are removed rather than preserved as aliases
   - `/triage-architecture` is installed when the package includes the
     architecture-audit lane
   - `ui_scout` is documented only when the package includes the UI
     product-truth lane
   - `init-project` seeds Ideal/spec first, then imports the appropriate package
   - do not create provider-specific skill variants when standard `SKILL.md`
     discovery from `.agents/skills` is sufficient
   - generate command aliases only when a repo explicitly keeps typed
     slash-command UX as a separate compatibility surface
   - run `scripts/sync-agent-skills.sh`
   - validate with `scripts/sync-agent-skills.sh --check`

11. **Audit and summarize**:
   - reference audit for stale phased-setup language
   - surface audit confirming the removed setup commands are no longer active
   - eval workflow audit (`create-eval` vs `improve-eval`)
   - triage/loop-verify surface audit
   - short alignment sweep across Ideal / Spec / State / Stories / Evals / ADRs

## Outputs

- Canonical setup skill surface installed
- Existing project-specific Ideal/spec preserved, reviewed, and aligned
- Working copy of `docs/setup-checklist.md`
- Runbook + AGENTS docs aligned to the same package
- Baseline golden/eval/story bootstrap included or explicitly deferred by repo
  variant
- Core story-loop skill surfaces installed or refreshed with sidecar,
  plan-gated delegation, parallel validation, and loop-verify escalation
  guardrails
- Fresh-doc dependency guidance installed for drift-prone providers,
  components, SDKs, model/provider slugs, tooling plugins, and framework APIs
- Outcome-first prompt contract guidance installed without deleting
  failure-proven local guardrails
- Upgraded triage, triage-health, sparse facts, and loop-verify surfaces
  installed or explicitly deferred by lane
- Canonical `.agents/skills` packages and cheap compatibility links checked;
  provider-specific command aliases generated only when explicitly retained
- Local runtime launcher installed or explicitly deferred according to whether
  the repo has a real browser/API/runtime surface

## Guardrails

- Do not teach multiple competing setup models in AGENTS or docs.
- Do not fabricate a generic `docs/ideal.md` or `docs/spec.md`; use
  `/init-project` for greenfield idea intake first.
- Do not recreate or advertise the removed phased setup skills.
- Do not treat old setup notes or retrofit notes as canonical bootstrapping
  docs once the runbook exists; mark them historical/superseded instead.
- Do not split day-zero bootstrap from golden/eval setup unless the user
  explicitly chooses to defer them.
- Do not create a new methodology shape in one doc and leave the old shape in
  the skill surface or `init-project`.
- Do not make sidecar or subagent guidance mandatory for routine story
  creation, no-code setup, ordinary refreshes, or small validation passes.
- Do not run long subagent verification loops in a no-code repo just to prove
  that code-dependent evidence does not exist yet. Install the sparse package,
  mark absent/deferred lanes, run cheap checks, and let later real code create
  real evidence.
