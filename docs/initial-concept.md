# Battle Map Projection Assistant — Working Product Spec

## 1. Project Summary

Build a portable tabletop tool that helps a Dungeon Master quickly project an RPG module map onto a physical 1-inch gridded battle mat.

The product is **not** a full VTT replacement. It is a **battlefield setup accelerator** for physical play.

Core promise:

> Take a quick photo of a module map, clean/de-skew it, hide player-invisible information, align it to the physical 1-inch grid, and project it onto the battle mat so the DM can immediately run the encounter, draw the room, or place physical terrain.

The product should optimize for **time-to-action**. The target experience is closer to:

> “I open the module to room 12, take a picture, mask/clean what the players should not see, hit Project, nudge if needed, and keep playing.”

Not:

> “Prepare a full digital VTT map ahead of the session.”

---

## 2. Core Use Case

The DM is running a printed or PDF RPG module. The party enters a room or encounter area. Normally, the DM would need to:

1. Look at the module map.
2. Count squares.
3. Draw the room on a wet-erase battle mat.
4. Possibly mark walls, doors, stairs, terrain, traps, etc.
5. Then another player/DM assistant may place magnetic/physical terrain over the drawn lines.

This causes downtime right when action should be dramatic.

The proposed system reduces that friction by projecting the relevant map or room geometry directly onto the mat. The DM can either:

- leave the projected map visible during play,
- quickly trace the projected walls/doors onto the mat,
- or use it as a placement guide for physical terrain.

The highest-value scenario is **fast encounter setup at a physical table**.

---

## 3. Product Identity

This should be thought of as:

> **Instant module-map-to-battle-mat projection.**

Not:

- a VTT,
- an animated map system,
- a campaign manager,
- a digital tabletop replacement,
- or a pre-authored map library product first.

The system should support advance prep, but the primary design pressure is live-table speed.

---

## 4. Hardware Concept

### 4.1 Preferred Hardware

Use a small integrated or semi-integrated rig:

- pico projector,
- camera mounted rigidly to the projector,
- phone/tablet as controller,
- optional Raspberry Pi / mini PC / laptop as processor during prototyping,
- USB-C power bank or wall power.

The camera should be mounted directly to the projector body or projector mount so the relative camera/projector geometry is fixed.

### 4.2 Why Camera Mounted to Projector

Mounting the camera to the projector makes the internal camera-projector relationship repeatable. This does **not** remove the need for per-placement calibration, because the projector may be placed at different angles/distances from the mat each time.

But it does make the calibration problem much more constrained and solvable.

Each setup still needs to determine:

- where the physical battle mat plane is,
- how the projector is angled relative to the mat,
- where the real 1-inch grid lies,
- what area of the table the projector covers,
- how projected pixels land on the mat.

### 4.3 Physical Placement

The rig should not assume overhead mounting.

Likely real-world use:

- sitting on the table,
- clamped to the table edge,
- roughly 8 inches or so above the tabletop,
- projecting from a skewed angle.

This means the system must handle:

- severe keystone distortion,
- skewed camera view,
- table-plane homography,
- shadows from hands/minis/terrain,
- uneven focus/brightness across the projection.

This is acceptable because the primary use is often **project first, draw/build quickly, then optionally turn off**.

---

## 5. Why Projector, Not Laser

A laser line system initially sounds attractive because many use cases only need “show me the walls.” However, a projector is probably the better MVP and product direction.

A laser implementation would likely require:

- galvos,
- pan/tilt mechanics,
- or multiple fixed line lasers,
- plus eye-safety considerations.

A pico projector is simply a 2D display. Once calibrated, it can show:

- full map imagery,
- wall outlines,
- doors,
- fog masks,
- reveal states,
- area-of-effect templates,
- terrain placement guides,
- calibration patterns.

The projector version is more flexible and likely easier to prototype.

---

## 6. Core Workflow

### 6.1 Live Table Workflow

1. DM opens a printed/PDF module map.
2. DM takes a phone photo of the map.
3. App auto-crops, de-skews, straightens, and contrast-normalizes the map.
4. DM masks unexplored areas using a Fog/Mask tool.
5. DM removes player-invisible marks inside visible areas using a Clean/Hide Pen.
6. Projector/camera rig calibrates itself against the physical battle mat grid.
7. DM taps Project.
8. Projected map appears aligned to the 1-inch mat grid.
9. DM can nudge, scale, rotate, brighten/dim, or switch between Map and Outlines modes.

### 6.2 Prepared Workflow / Map Library Workflow

1. DM imports or photographs maps before the session.
2. App normalizes each map.
3. DM optionally runs Auto-Clean.
4. DM reviews/corrects AI changes.
5. App stores:
   - original photo,
   - normalized map,
   - player-safe edit layers,
   - outline version,
   - scale metadata,
   - reveal/fog layers.
6. During play, DM opens the saved map and projects immediately.

Prepared workflow is a nice-to-have. It should not be required.

---

## 7. Core Map Data Model

Every imported map should be treated as a **non-destructive layer stack**.

### 7.1 Canonical Map Object

A map should store:

1. **Original Photo**
   - Raw phone image.
   - Never destructively modified.

2. **Normalized Base**
   - Cropped.
   - De-skewed.
   - Perspective-flattened.
   - Contrast-normalized.
   - Grid-straightened if possible.
   - This becomes the stable working coordinate space.

3. **Detected Source Grid Metadata**
   - Grid origin.
   - Grid spacing in pixels.
   - Grid rotation.
   - Source scale, e.g. 5 ft/square or 10 ft/square.
   - Confidence score.
   - Manual overrides.

4. **Privacy/Edit Layers**
   - Fog/mask regions.
   - Clean/inpaint regions.
   - Manual erase strokes.
   - Auto-clean proposed patches.
   - Restored regions.
   - Undo/redo history.

5. **Display Layers**
   - Map view.
   - Outlines view.
   - Optional grid overlay.
   - Projection brightness/contrast adjustments.

6. **Projection Transform**
   - Normalized map coordinates → physical battle mat coordinates.
   - Battle mat coordinates → projector pixel coordinates.
   - Nudge/rotate/scale state.

### 7.2 Key Principle

Never flatten edits destructively into the source image.

The DM must be able to:

- reveal more of the dungeon,
- undo a mask,
- restore a cleaned trap marker if needed,
- correct AI mistakes,
- switch between Map and Outlines,
- re-project at a later session.

---

## 8. Capture and Normalization

### 8.1 First Processing Step

The first step after capture should be:

> Normalize the map into a clean, flat, top-down working image.

The DM may take a bad photo:

- from an angle,
- from a printed book,
- from a curved page,
- with uneven lighting,
- with shadows,
- with weak contrast.

The app should attempt to:

- find the map bounds,
- crop the map,
- de-skew perspective,
- straighten the grid,
- clean up contrast,
- reduce shadows/glare where possible,
- produce a stable “normalized base.”

### 8.2 User Control

The DM should be able to correct normalization quickly:

- drag crop corners,
- rotate 90 degrees,
- manually set grid direction,
- manually choose two or more grid intersections,
- undo auto-enhancement if it made things worse.

Normalization should be fast and local. It should not rely on a 30-second AI pass.

---

## 9. Privacy Tools

There are two distinct privacy problems. They need different tools.

### 9.1 Fog / Mask Tool

Purpose:

> Hide areas the players have not reached or cannot see.

Use for:

- unexplored rooms,
- corridors beyond doors,
- map sections outside the current room,
- areas beyond secret doors,
- later reveal regions.

This is overt. Players understand that masked/fogged areas are simply unseen.

The DM should be able to:

- paint fog manually,
- use rectangles/polygons/lasso,
- erase fog to reveal more,
- save reveal states,
- undo/redo.

### 9.2 Clean / Hide Pen

Purpose:

> Remove information that exists only for the DM but is located inside an otherwise visible area.

Use for:

- room numbers,
- trap markers,
- secret door symbols,
- treasure labels,
- keyed object numbers,
- DM notes,
- hidden annotations.

This should behave like a Photoshop-style healing/inpainting brush. The DM swipes over the unwanted mark and the app reconstructs the floor, wall, hatching, furniture, grid, or nearby texture underneath.

This is critical because simply masking an “S” or trap symbol inside a room would reveal that something is there.

---

## 10. Auto-Clean Mode

### 10.1 Auto-Clean Should Be Optional

Auto-clean should not be a required step in live play.

Reason:

- It may take ~30 seconds.
- Some maps are already player-safe.
- Some maps only need 5 seconds of manual masking/inpainting.
- Waiting for AI every time would violate the time-to-action goal.

Auto-clean should be a separate command, useful for:

- prep before a session,
- maps with many room numbers/secrets/trap labels,
- generating a polished player-safe version,
- preparing maps for the library.

### 10.2 Auto-Clean Function

Input:

- normalized base map.

Prompt/goal:

> Redraw this map to remove secrets, traps, room numbers, DM notes, and other player-invisible markings. Keep normally visible map features such as doors, statues, walls, stairs, floors, furniture, and visible terrain. Do not include areas beyond secret doors if those areas should not be visible.

Output:

- cleaned player-safe map image.

### 10.3 Auto-Clean Review

The AI output should never be blindly trusted.

The DM should be able to:

- compare original vs cleaned,
- see changed regions,
- accept/reject individual changes,
- restore original content in selected regions,
- clean more manually,
- save the accepted result as edit layers.

---

## 11. AI Diff as Editable Inpaint Regions

If Auto-Clean is run against the normalized base, and the AI returns an image in the same geometry, then the app can diff the two images.

### 11.1 Diff Workflow

1. Normalize source map.
2. Send normalized map to AI Auto-Clean.
3. Receive cleaned image.
4. Compare original normalized base vs cleaned image.
5. Detect changed regions.
6. Cluster changed pixels into localized patches.
7. Convert those patches into editable “inpaint regions.”
8. Let DM accept, reject, restore, or modify individual patches.

### 11.2 Why This Matters

The AI result should become a **proposed edit layer**, not a destructive replacement bitmap.

This means:

- if AI removes a trap marker, the DM can later reveal/restore it,
- if AI accidentally changes a door or wall, the DM can reject that patch,
- if AI cleans too much, changes remain inspectable,
- if AI misses something, the DM can manually clean it.

### 11.3 Diff Caveat

Naive pixel-diff may be too noisy because image generation/inpainting may subtly alter:

- hatching,
- paper texture,
- grid line strength,
- wall shading,
- contrast,
- small textures.

The diff system should therefore:

- ignore tiny low-contrast changes,
- prefer localized high-confidence changes,
- cluster nearby changes,
- suppress broad texture shifts,
- possibly compare edges/text-like features rather than raw pixels only,
- present the result as reviewable suggestions.

---

## 12. Display Modes

Keep DM-facing modes simple.

### 12.1 Map Mode

Shows the cleaned, player-safe map image.

Use when:

- projection quality is good enough,
- the DM wants the actual room imagery visible,
- players would enjoy seeing map art/texture,
- physical terrain is not blocking the projection too much.

### 12.2 Outlines Mode

Shows simplified high-contrast geometry:

- walls,
- doors,
- stairs,
- pillars,
- pits,
- major terrain edges,
- object silhouettes if useful.

Use when:

- the DM wants to draw the map quickly,
- another player is placing magnetic terrain,
- the full map is too visually busy,
- the projection is being used as a construction guide.

Outlines mode may eventually be generated using CV/AI, but it can begin as a high-contrast/edge-detection view plus manual cleanup.

---

## 13. Projection Calibration

### 13.1 Dynamic Calibration

The projector/camera rig should dynamically calibrate each time it is placed.

Ideal flow:

1. Rig is placed on table or clamped nearby.
2. App turns on camera.
3. Projector displays calibration dots/pattern.
4. Camera observes:
   - physical battle mat grid,
   - projected calibration points.
5. App computes projection transform.
6. Meanwhile, DM edits/fogs/cleans the map on phone.
7. When both are ready, DM taps Project.

### 13.2 What Calibration Computes

The system needs to solve:

- real battle mat grid in camera space,
- projector pixel locations on the mat,
- mapping from normalized map grid to real mat grid,
- mapping from real mat grid to projector pixels.

Since the battle mat is flat, the core geometry can be treated as a planar homography problem.

### 13.3 Battle Mat Grid Detection

The physical battle mat is assumed to have a visible 1-inch square grid.

The camera should detect:

- two dominant families of parallel grid lines,
- grid intersections,
- grid angle,
- grid spacing,
- usable visible grid region.

The grid may be skewed heavily in the camera image because the projector/camera rig is not overhead.

### 13.4 Manual Fallback

Do not rely only on full-auto grid detection.

Include a fast manual fallback:

- “Tap one visible grid intersection.”
- “Drag along grid direction.”
- “Select two points 5 squares apart.”
- “Project test grid and nudge/scale/rotate.”

The system should be robust in the presence of:

- glare,
- wet-erase marker lines,
- terrain shadows,
- character sheets/papers on the mat,
- minis,
- projected content confusing the camera.

Calibration should ideally happen before projecting the actual map.

---

## 14. Scaling and Grid Rules

### 14.1 Source Map Scale May Differ from Battle Mat Scale

Many RPG module maps use 10-foot squares. A normal D&D battle mat usually treats each 1-inch physical square as 5 feet.

Therefore:

> One source map square may need to become 2 × 2 physical battle mat squares.

This needs to be a first-class feature.

### 14.2 Scale Metadata

The app should store:

- source grid square size, e.g. 5 ft, 10 ft, custom,
- physical mat square size, usually 5 ft,
- pixels per source square in normalized map,
- physical squares per source square,
- scale confidence.

### 14.3 Scale Detection

If the scale label is visible, such as “1 square = 10 feet,” the app can try to detect it using OCR/AI.

But the DM must be able to override scale manually.

### 14.4 Scale Controls

Required controls:

- source square = 5 ft,
- source square = 10 ft,
- source square = custom,
- physical square = usually 5 ft,
- snap source grid to mat grid,
- nudge by one physical square,
- nudge by one source square,
- rotate 90 degrees.

---

## 15. DM UI Principles

### 15.1 Phone as Controller

The phone is likely best used for:

- taking photos of module maps,
- masking/fogging,
- inpainting/cleaning,
- selecting saved maps,
- projection controls.

The phone should not be the projection-calibration camera. The projector rig should have its own camera because it needs to see the table/projector relationship.

### 15.2 Required Live Controls

Keep controls minimal:

- Project / Stop Projecting.
- Map / Outlines toggle.
- Fog/Mask tool.
- Clean/Hide Pen.
- Erase/Reveal.
- Undo / Redo.
- Nudge up/down/left/right.
- Rotate 90 degrees.
- Scale source grid.
- Brightness/contrast.
- Recalibrate.

### 15.3 UX Priority

The UI should prefer speed over perfection.

A slightly imperfect projection in 20 seconds is more useful than a perfect one after 5 minutes.

---

## 16. MVP Scope

### 16.1 MVP Goal

Prove that a DM can go from a module map photo to a usable tabletop projection quickly enough to improve live play.

### 16.2 MVP Features

Minimum viable product:

- phone/photo import,
- crop/de-skew/contrast normalization,
- manual source grid setup,
- fog/mask tool,
- clean/hide pen using local inpainting or simple healing,
- projector output,
- manual/four-point table calibration,
- nudge controls,
- rotate 90 degrees,
- scale controls including 5 ft/10 ft source grid,
- Map mode,
- basic Outlines mode,
- save/load map project.

### 16.3 MVP Non-Goals

Do not start with:

- full VTT features,
- monster tokens,
- initiative tracking,
- animated maps,
- complex lighting/fog-of-war simulation,
- mandatory AI auto-clean,
- huge map library marketplace,
- laser hardware.

---

## 17. Implementation Notes

### 17.1 Suggested Prototype Stack

Possible prototype stack:

- Python + OpenCV for calibration/de-skew/grid detection.
- Web app or React Native app for phone UI.
- Local web server on mini PC/Raspberry Pi/laptop.
- HDMI pico projector as display output.
- USB camera mounted to projector.
- ImageMagick/OpenCV/Pillow for image operations.
- Optional AI image inpainting via external model/API for Auto-Clean and Clean Pen.

### 17.2 Geometry Pipeline

Conceptual transforms:

1. `originalPhoto -> normalizedMap`
2. `normalizedMapGrid -> sourceMapFeet`
3. `sourceMapFeet -> physicalBattleMatSquares`
4. `physicalBattleMatSquares -> tablePlaneCoordinates`
5. `tablePlaneCoordinates -> projectorPixels`

### 17.3 Calibration Data

Store calibration per placement/session, not permanently as part of the map.

Store source map normalization and edit layers with the map project.

### 17.4 Layer Rendering

Render final projected image from:

- normalized base,
- accepted inpaint patches,
- fog/mask layer,
- chosen display mode,
- projection transform.

---

## 18. Open Questions

1. How large an encounter area can a low side-mounted pico projector cover acceptably?
2. How bad is focus falloff when projecting from ~8 inches up at a skewed angle?
3. How often does terrain/minis/shadows break projection usefulness?
4. Is live Map mode good enough visually, or is Outlines mode the real core feature?
5. How accurate does auto grid detection need to be before manual nudge is “good enough”?
6. How fast can local inpainting be made for the Clean/Hide Pen?
7. Should Auto-Clean use a cloud AI service initially, or be deferred entirely?
8. How should secret-door-connected hidden spaces be detected or handled safely?
9. How much of source map scale detection can be automated reliably from labels like “10 feet”?
10. Is the best first hardware prototype laptop + projector + webcam, before shrinking to a portable rig?

---

## 19. Design North Star

The system succeeds if it lets a DM preserve the pacing of a physical RPG session.

The ideal moment:

> The players kick open the door. The DM takes or opens the map, masks what they cannot see, hits Project, and the room appears aligned on the mat before the table loses momentum.

Speed matters more than polish.

Reversibility matters more than automation.

Physical-table usefulness matters more than VTT completeness.
