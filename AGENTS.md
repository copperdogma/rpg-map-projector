# Agent Instructions

## Project Shape

This repo is a hardware-assisted product prototype for live tabletop RPG play. Treat it primarily as a projection/calibration product, secondarily as a local web gateway and computer-vision app.

The likely finished home setup is:

- Raspberry Pi or similar mini-computer as the local gateway,
- off-the-shelf HDMI projector,
- fixed webcam mounted to the projector,
- phone or iPad as the DM controller,
- optional remote storage/auth server after the MVP.

The laptop is only the current stand-in for the future gateway.

## Source Of Truth

Read these in order:

1. `docs/ideal.md` — product north star.
2. `docs/spec.md` — category-aligned product/architecture spec.
3. `docs/methodology/state.yaml` — methodology state and deferred lanes.
4. `docs/methodology/graph.json` — generated graph.
5. Active story files under `docs/stories/`.
6. `docs/scout.md` and `docs/scout/` when external evidence is needed.
7. ADRs under `docs/decisions/` when a hard-to-reverse decision is involved.

`docs/initial-concept.md` is preserved raw intake. Do not rewrite it into polished project docs.

`docs/stories.md` is generated. Edit story files and rerun `make methodology-compile`.

## Operating Rules

- Favor proof stories that reduce physical feasibility risk over stories that only add scaffolding.
- Do not turn the product into a VTT, campaign manager, token tracker, animated-map system, or map marketplace unless the Ideal/spec deliberately change.
- Treat speed at the physical table as a hard product constraint. A slightly imperfect projection in seconds is usually better than a polished result after minutes.
- Keep edits reversible and non-destructive: source images, normalized maps, masks, clean patches, and projection transforms should remain separable.
- Keep live projection local-first. Remote storage/auth is expected later for prep and sync, but it is not part of the MVP and must not become required for live play.
- Start with a gateway-hosted web UI. Native iOS stays deferred until the web workflow proves the value and limitations.
- Use QR-code pairing as the default discovery idea for the DM device opening the local gateway UI.
- Keep runtime launchers tied to Conductor's local port allocation. Do not add
  UI scouts, codebase scans, or eval harnesses before real evidence warrants
  them.
- Use `docs/scout/` for external evidence before hardware, library, SDK, auth/storage, or architecture adoption.
- Use ADRs for hard-to-reverse choices such as gateway/server boundaries, native app adoption, calibration architecture, and hardware requirements.

## Methodology Commands

```bash
make methodology-compile
make methodology-check
make skills-sync
make skills-check
make triage-facts-check
make local-status
```

## Local Runtime

Use the allocation-backed launcher instead of raw Vite defaults:

```bash
npm run local:app
npm run local:status
npm run local:stop
```

The primary checkout uses `http://127.0.0.1:5178/` for the controller and
`http://127.0.0.1:5178/projector.html` for the projector view. Worktrees derive
stable ports from Conductor's `rpg-map-projector` allocation.

## Prototype Bias

Until hardware proves otherwise, assume:

- laptop-as-gateway for development,
- HDMI projector for display,
- iPhone remote camera or cheap webcam fixed to the projector,
- manual calibration fallback before full automation,
- OpenCV-style geometry experiments before polished UI.

## Validation Bias

For early work, validation should be concrete and physical when possible:

- test against a real or printed 1-inch grid,
- capture screenshots or photos of projected calibration output,
- record alignment error in physical squares or inches,
- time the workflow from source map to useful projection.

Do not commit or push unless the user explicitly asks.
