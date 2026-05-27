# RPG Map Projector

RPG Map Projector is a tabletop tool for turning module maps into fast, usable battle-mat projections during physical RPG play.

The project is not trying to become a VTT. The core product promise is:

> Capture or open a module map, clean and mask what players should not see, align it to a real 1-inch battle mat, and project it quickly enough that the table keeps moving.

## Current Direction

The first build path assumes a generic prototype rig:

- laptop as the processing/control machine,
- HDMI pico/projector output,
- iPhone used as a fixed-position remote camera,
- a temporary cardboard or printed mount that slots the phone against the projector,
- a physical 1-inch gridded battle mat.

The phone-mounted-to-projector setup is meant to keep camera/projector geometry repeatable while still requiring per-placement calibration against the mat.

## First Proof

Story 001 is a calibration and projection spike. It should prove that a rough projector/camera setup can map a source grid onto the real mat well enough for a DM to trace walls, place terrain, or run an encounter without losing session momentum.

## Project Docs

- [docs/initial-concept.md](docs/initial-concept.md) preserves the raw kickoff seed.
- [docs/ideal.md](docs/ideal.md) states the north star and product values.
- [docs/spec.md](docs/spec.md) distills the product spec from the seed.
- [docs/assumptions.md](docs/assumptions.md) tracks early hardware and feasibility assumptions.
- [docs/stories/story-001-calibration-projection-spike.md](docs/stories/story-001-calibration-projection-spike.md) defines the first proof story.
