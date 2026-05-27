# Product Spec: Battle Map Projection Assistant

## Summary

Build a portable tabletop tool that projects RPG module maps onto a physical 1-inch gridded battle mat.

The product accelerates battlefield setup for physical play. It should let a DM capture or import a module map, normalize it, hide player-invisible information, align it to the real mat grid, and project either map imagery or simplified outlines.

## Target Workflow

### Live Table Workflow

1. DM opens a printed or PDF module map.
2. DM captures a photo or imports the map.
3. App crops, de-skews, straightens, and contrast-normalizes the map.
4. DM masks unexplored areas.
5. DM cleans room numbers, trap marks, secret-door marks, and other DM-only details.
6. Projector/camera rig calibrates against the physical mat.
7. DM taps Project.
8. Map appears aligned to the 1-inch grid.
9. DM nudges, rotates, scales, brightens, or switches display mode as needed.

### Prepared Workflow

1. DM imports or photographs maps before a session.
2. App normalizes each map.
3. DM optionally runs Auto-Clean.
4. DM reviews proposed edits.
5. App stores original image, normalized base, edit layers, display settings, and source scale metadata.
6. During play, DM opens the saved map and projects immediately.

Prepared workflow is useful, but live capture must remain first-class.

## Prototype Hardware Path

Initial work should assume:

- laptop for processing and app hosting,
- HDMI projector for display,
- iPhone as a remote camera,
- phone held in a fixed slot or mount attached to the projector,
- real 1-inch battle mat as calibration target.

The fixed phone/projector relationship should make internal geometry repeatable. Each placement still needs dynamic calibration because the rig may sit at different distances, heights, and angles.

The prototype should not assume overhead mounting. Side or table-edge placement is expected.

## Core Map Model

Each imported map is a non-destructive layer stack:

- original photo or source image,
- normalized base image,
- detected source-grid metadata,
- manual grid overrides,
- fog/mask regions,
- clean/inpaint regions,
- auto-clean proposed patches,
- display mode settings,
- projection transform state for the current session.

Edits must not flatten destructively into the original source.

## Capture And Normalization

The first processing step after capture is to produce a clean, flat, top-down working image.

Required behavior:

- find map bounds,
- crop,
- de-skew perspective,
- straighten or define the grid,
- normalize contrast,
- reduce shadows or glare when practical,
- allow manual correction.

Manual controls must include crop corners, rotation, grid direction, grid intersections, and undo for bad enhancement.

## Privacy Tools

### Fog / Mask

Fog hides regions the players have not reached or cannot see.

Required controls:

- paint fog,
- rectangle/polygon/lasso fog,
- erase/reveal,
- save reveal state,
- undo/redo.

### Clean / Hide Pen

Clean removes DM-only marks inside otherwise visible space.

Use cases:

- room numbers,
- trap markers,
- secret door symbols,
- treasure labels,
- keyed object numbers,
- DM notes.

The tool should behave like a healing or inpainting brush and should avoid revealing that something was hidden.

## Auto-Clean

Auto-Clean is optional and should not block live play.

It may be used for prep or complex maps. Output should become proposed edit layers, not a replacement bitmap. The DM must be able to compare, accept, reject, restore, and manually adjust suggested changes.

## Display Modes

### Map Mode

Projects the cleaned player-safe map image.

### Outlines Mode

Projects high-contrast geometry for tracing, terrain placement, or low-clarity projection environments.

Outlines may begin with edge detection and manual cleanup before more advanced CV or AI generation.

## Calibration

Each placement needs dynamic calibration against the physical mat.

The system should compute:

- battle-mat grid in camera space,
- projected calibration points in camera space,
- map grid to physical mat coordinates,
- physical mat coordinates to projector pixels.

The core geometry can be treated as planar homography while the mat is flat.

Full automatic grid detection is desirable, but manual fallback is required:

- tap a grid intersection,
- mark grid direction,
- select two points a known number of squares apart,
- project a test grid,
- nudge, scale, and rotate.

## Scale Rules

Source maps may use 5 ft, 10 ft, or custom square scales. A 10 ft source square should be able to cover 2 by 2 physical 5 ft mat squares.

Required controls:

- source square = 5 ft,
- source square = 10 ft,
- source square = custom,
- physical square = usually 5 ft,
- snap source grid to mat grid,
- nudge by physical square,
- nudge by source square,
- rotate 90 degrees.

## DM Controller UI

The controller should prioritize speed:

- Project / Stop Projecting,
- Map / Outlines,
- Fog / Mask,
- Clean / Hide Pen,
- Erase / Reveal,
- Undo / Redo,
- Nudge,
- Rotate 90 degrees,
- Scale source grid,
- Brightness / contrast,
- Recalibrate.

The phone may be used as the remote camera in early prototypes, but the controller UI can run on the laptop until the physical path is proven.

## MVP Exploration Direction

The MVP is not the product spec. It is the exploration path for proving the spec.

Early work should prove:

- source grid can be mapped to physical mat grid,
- laptop + projector + iPhone camera can support calibration,
- alignment can be corrected quickly by a DM,
- projection is useful enough for tracing or terrain placement,
- Map mode or Outlines mode has the stronger table value.

## Open Questions

- How large an encounter area can the projector cover from realistic table placement?
- How severe is focus falloff from a skewed projector angle?
- Can an iPhone remote camera provide stable enough frames for calibration?
- How well does a cardboard or printed mount preserve camera/projector geometry?
- Is Map mode visually useful in real lighting, or is Outlines mode the main workflow?
- How accurate does calibration need to be before manual nudge is good enough?
- How fast can Clean/Hide work locally?
- When, if ever, should cloud AI be part of live play?
