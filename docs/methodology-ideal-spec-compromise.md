# Ideal-First Methodology

This repo starts from the Ideal and treats the spec as the current map of constraints, tradeoffs, and proof surfaces.

- `docs/ideal.md` is the north star: what the product should feel like when it works.
- `docs/spec.md` is the category-aligned product and architecture map, with stable `spec:N` and `spec:N.N` anchors.
- `docs/methodology/state.yaml` tracks which categories and compromises have real substrate.
- `docs/methodology/graph.json` is generated from the spec, state, stories, ADRs, and eval registry.
- `docs/stories.md` is generated. Edit story files under `docs/stories/` instead.

The point is not to add process. The point is to keep later implementation work tied to the same product truth: live physical-table speed, local gateway projection, web-first control, and remote storage/auth as a post-MVP layer.

## Constraint Phases

- `climb`: active uncertainty that needs proof or design work.
- `hold`: accepted compromise for now.
- `converge`: ready to simplify, delete, or replace.

## Sparse Setup Notes

This repo has no implementation yet. The following lanes are intentionally deferred:

- automated eval/golden harnesses,
- browser/UI scout,
- local runtime launcher,
- codebase-improvement scans,
- architecture audits.

They should be added when real code or runtime surfaces exist.
