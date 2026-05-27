# Ideal: Battle Map Projection Assistant

## North Star

A Dungeon Master should be able to turn a module map into a usable physical battle-mat projection fast enough that the table never feels the setup delay.

The ideal moment:

> The players open the door, the DM captures or opens the room map, hides what the players should not see, taps Project, and the battlefield appears aligned on the real mat before the scene loses momentum.

## Product Identity

This is an instant module-map-to-battle-mat projection assistant.

It is not a VTT, a campaign manager, an animated map system, a token tracker, or a replacement for physical terrain. It exists to accelerate physical play.

## Product Values

### Speed Over Polish

The product should optimize time-to-action. A useful projection in 20 seconds beats a perfect map after 5 minutes.

### Physical Table First

The system should help a real table: wet-erase mats, physical minis, terrain, hands, shadows, imperfect projector placement, and limited space.

### Reversibility Over Automation

Source images and edits must stay non-destructive. The DM should be able to reveal, undo, restore, compare, and correct without losing the original map.

### Robust Manual Control

Automation is useful only when it stays out of the way. Every critical step needs a fast manual fallback: crop, grid, scale, calibration, nudge, mask, reveal, and clean.

### Player-Safe Projection

The system must distinguish between unseen areas and DM-only marks inside visible areas. Fog can hide unrevealed space; clean/hide tools must remove room numbers, traps, secret doors, and labels without telegraphing secrets.

### Calibration Is Product Core

The map is only useful if it lands on the mat. Projector/camera calibration, source-grid scale, physical-grid alignment, and fast correction are core product behavior, not implementation details.

## Success Criteria

The project is working when a DM can:

- capture or import a module map during play,
- normalize it into a clean top-down working image,
- hide player-invisible information quickly,
- align 5 ft and 10 ft source grids to a real 1-inch mat,
- project Map or Outlines mode with usable accuracy,
- correct alignment with simple controls,
- save map work without flattening the source,
- preserve live-session pacing.

## Non-Goals

The product should not optimize for:

- full VTT feature parity,
- monster/token management,
- initiative tracking,
- animated maps,
- complex dynamic lighting,
- a giant map marketplace,
- mandatory AI processing,
- laser hardware as the default direction.
