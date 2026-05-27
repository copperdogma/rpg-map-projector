# ADRs

Architecture Decision Records live here.

Use an ADR when a project-level product, hardware, data-model, workflow, storage/auth, or architecture choice is hard to reverse or likely to shape several future stories.

Do not create ADRs for ordinary implementation tasks. Use a story instead.

## Layout

```text
docs/decisions/
  adr-001-example.md
  research/
    adr-001-example-research-prompt.md
    adr-001-example-final-synthesis.md
```

## Statuses

- `Proposed` - decision exists, but research or discussion is still needed
- `Accepted` - decision made and reflected in the relevant project plan
- `Rejected` - explicitly decided against
- `Deferred` - not needed yet; record the trigger to reopen
- `Superseded` - replaced by a newer ADR

## Early ADR Candidates

- local gateway responsibilities versus remote server responsibilities,
- remote storage/auth model after MVP,
- native iOS adoption trigger,
- camera/projector hardware requirements,
- calibration architecture if the first proof exposes a hard choice.
