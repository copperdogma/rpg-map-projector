# RPG Map Projector

RPG Map Projector is a tabletop tool for turning module maps into fast, usable battle-mat projections during physical RPG play.

The project is not trying to become a VTT. The core product promise is:

> Capture or open a module map, clean and mask what players should not see, align it to a real 1-inch battle mat, and project it quickly enough that the table keeps moving.

## Current Direction

The first build path uses a laptop as a stand-in for the eventual local gateway:

- laptop temporarily doing the gateway work,
- HDMI projector output,
- iPhone remote camera or cheap webcam as the calibration camera,
- a temporary cardboard, taped, or printed mount that fixes the camera to the projector,
- a physical 1-inch gridded battle mat.

The likely finished home setup is a Raspberry Pi or similar mini-computer connected to an off-the-shelf HDMI projector and fixed webcam. The DM connects from a phone or iPad to a local web interface, likely by scanning a QR code shown by the projector/gateway, while the gateway owns camera input, projector output, calibration, and projection alignment.

A remote storage/auth server is expected later for prep away from the table, but live projection starts local-first so the MVP and table workflow do not depend on internet access.

## First Proof

Story 001 is a calibration and projection spike. It should prove that a rough projector/camera setup can map a source grid onto the real mat well enough for a DM to trace walls, place terrain, or run an encounter without losing session momentum.

The current Story 001 prototype is a local browser workbench:

- controller view: `http://127.0.0.1:5178/`
- projector view: `http://127.0.0.1:5178/projector.html`
- fixture labeler: `http://127.0.0.1:5178/labeler.html`
- optional false camera inputs can be placed in `input/map-pix/`; this folder is ignored by git because the local test photos may be third-party sales images.
- benchmark grid labels are saved to `input/map-grid-labels.json` from the fixture labeler.

Run it with:

```bash
npm install
npm run local:app
```

The local launcher reads Conductor's port allocation from
`/Users/cam/Documents/Projects/conductor/local-dev-ports.json`. The primary
checkout uses UI port `5178`; worktrees receive stable ports from the
`5900-5999` range. Use `npm run local:status` to inspect the current process
and `npm run local:stop` to stop only this checkout's launcher-owned service by
default.

## Project Docs

- [docs/initial-concept.md](docs/initial-concept.md) preserves the raw kickoff seed.
- [docs/ideal.md](docs/ideal.md) states the north star and product values.
- [docs/spec.md](docs/spec.md) distills the product spec from the seed.
- [docs/assumptions.md](docs/assumptions.md) tracks early hardware and feasibility assumptions.
- [docs/stories/story-001-calibration-projection-spike.md](docs/stories/story-001-calibration-projection-spike.md) defines the first proof story.
- [docs/scout.md](docs/scout.md) indexes external research and hardware/library scouting.
- [docs/decisions/README.md](docs/decisions/README.md) describes ADRs for hard-to-reverse choices.

## Methodology

This repo uses a sparse greenfield methodology package:

- `docs/stories.md` is generated from story files.
- `docs/methodology/graph.json` is generated from Ideal/spec/state/stories/evals.
- `docs/scout/` holds external research and adoption decisions.
- `docs/decisions/` holds ADRs for sticky product, hardware, and architecture choices.
- Remote storage/auth, native iOS, eval harnesses, UI scout, and codebase scans
  are deferred until the physical proof or implementation substrate exists.
- The local runtime launcher is present for the Story 001 browser workbench and
  uses Conductor's assigned ports.

Useful checks:

```bash
make methodology-compile
make methodology-check
make skills-check
make triage-facts-check
make local-status
npm run check
```
