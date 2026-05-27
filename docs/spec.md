# Product Spec: Battle Map Projection Assistant

This spec is the durable product and architecture map. It is broader than the MVP. The MVP exists to test the riskiest parts of this spec rather than to redefine the desired product.

## spec:1 — Product Identity And Table Workflow

### spec:1.1 — Summary

Build a portable tabletop tool that projects RPG module maps onto a physical 1-inch gridded battle mat.

The product accelerates battlefield setup for physical play. It should let a DM capture or import a module map, normalize it, hide player-invisible information, align it to the real mat grid, and project either map imagery or simplified outlines.

Relevant scout: [Scout 001](scout/scout-001-existing-battle-map-projection-solutions.md) found close prior art in Mappadux / Dynamic Map Renderer v2 for fast image-to-player projection, but it should be treated as a useful reference rather than a product match because it trends toward full VTT features instead of module-map-to-physical-mat projection.

### spec:1.2 — Live Table Workflow

1. DM opens a printed or PDF module map.
2. DM captures a photo or imports the map.
3. App crops, de-skews, straightens, and contrast-normalizes the map.
4. DM masks unexplored areas.
5. DM cleans room numbers, trap marks, secret-door marks, and other DM-only details.
6. Projector/camera rig calibrates against the physical mat.
7. DM taps Project.
8. Map appears aligned to the 1-inch grid.
9. DM nudges, rotates, scales, brightens, or switches display mode as needed.

### spec:1.3 — Prepared Workflow

1. DM imports or photographs maps before a session.
2. App normalizes each map.
3. DM optionally runs Auto-Clean.
4. DM reviews proposed edits.
5. App stores original image, normalized base, edit layers, display settings, and source scale metadata.
6. During play, DM opens the saved map and projects immediately.

Prepared workflow is useful, but live capture must remain first-class.

**B1: Remote prep is expected later but excluded from MVP**

- Ideal: The DM can prep maps from a phone or iPad without turning on the projector gateway.
- Constraint: MVP work stays local-first and may not persist prepared maps beyond the live session.
- Limitation type: Execution and product sequencing.
- Detection: Physical projection workflow is proven and map project data needs to survive across sessions/devices.
- Residual form: Remote storage/auth becomes an additive sync layer, not a live-play dependency.

## spec:2 — Hardware Rig And Gateway Topology

### spec:2.1 — Prototype Rig

Initial development uses a laptop as a stand-in for the eventual local gateway:

- laptop temporarily handling processing, app hosting, camera input, and projector output,
- HDMI projector for display,
- iPhone remote camera or cheap webcam for calibration input,
- camera held in a fixed slot, taped mount, or printed mount attached to the projector,
- real 1-inch battle mat as calibration target.

### spec:2.2 — Finished Home Rig

The likely finished home setup should not require the DM to bring a laptop to the table. It should use a Raspberry Pi or similar mini-computer as a local gateway. The projector and fixed camera plug into that gateway, and the DM controls the system from a phone or iPad.

The fixed camera/projector relationship should make internal geometry repeatable. Each placement still needs dynamic calibration because the rig may sit at different distances, heights, and angles.

The prototype should not assume overhead mounting. Side or table-edge placement is expected.

**B2: Laptop-as-gateway is only a stand-in**

- Ideal: The table rig is a small dedicated local appliance.
- Constraint: Early development uses a laptop because the hardware is not chosen yet.
- Limitation type: Hardware availability.
- Detection: A projector, camera, and candidate mini-computer are available for measurement.
- Residual form: Laptop path remains a dev mode; table path moves to mini-computer.

**B3: Hardware requirements are unknown**

- Ideal: The gateway hardware is cheap, reliable, and strong enough for all local live-play work.
- Constraint: Required CPU/GPU, camera bandwidth, projector latency, and local image-operation costs are not measured yet.
- Limitation type: Unknown physical/runtime evidence.
- Detection: Story 001 or a follow-up hardware-sizing story records calibration latency, projection loop latency, image operation cost, and camera resolution needs.
- Residual form: Hardware shopping requirements replace assumptions.

## spec:3 — Software Architecture And Connectivity

### spec:3.1 — Local Web Interface

Start with a local web interface rather than a native iOS app.

The local gateway should host the first web UI, receive maps and edit commands from the DM device, read frames from the calibration camera, render the projector output, and keep the low-latency calibration/projection loop close to the hardware.

The gateway should support quick pairing by showing a QR code that opens the local web interface on the DM device. The first version can use this for local-network discovery. Later versions can use the same pairing idea to attach the local gateway to an authenticated remote account or prepared-map library.

Relevant scout: [Scout 001](scout/scout-001-existing-battle-map-projection-solutions.md) should be revisited when designing the local web controller, QR/room-code pairing, player/projector split, static/PWA hosting path, local browser storage, and PeerJS-style or gateway-native networking model.

### spec:3.2 — DM Device Role

The DM device should act as a controller/editor:

- capture or upload the source map,
- perform or request normalization,
- mask and reveal areas,
- issue clean/hide edits,
- send Project/Stop and alignment controls,
- nudge, scale, rotate, and adjust brightness while looking at the physical mat.

### spec:3.3 — Remote Server Direction

The project should remain local-first for live play, but the architecture should assume a remote server is likely after the MVP.

The remote server is most valuable for preparation away from the projector:

- DM captures maps before the session,
- DM opens the app without turning on the projector gateway,
- DM normalizes, masks, cleans, names, and organizes maps,
- map projects sync to the account,
- when the local gateway comes online, the DM can send a prepared map to it.

If remote storage exists, it likely needs authentication because maps, campaign notes, and reveal states are private. Auth should protect storage and sync. It should not become a hard requirement for projecting a local map during play.

The gateway should still be able to run a minimal local-only mode:

- host the web UI,
- accept a map from the DM device,
- calibrate,
- project,
- forget everything after the session unless explicit local save is added.

This split means early versions can avoid remote storage while still using stable concepts that will survive sync later: map project IDs, non-destructive layers, explicit save/send states, and a clear distinction between prepared map storage and live projection session state.

**B4: Web first, native iOS later**

- Ideal: The DM can use the best-feeling app surface for prep and live control.
- Constraint: The first version is a web page because it reduces setup, distribution, and platform friction.
- Limitation type: Execution sequencing.
- Detection: Web workflow works and a native app would materially improve capture, offline prep, local processing, or user experience.
- Residual form: Native app can become a client over the same gateway/server contracts.

**B5: Remote server is post-MVP**

- Ideal: Prepared maps sync across devices and sessions through authenticated remote storage.
- Constraint: MVP omits remote storage/auth so the physical projection loop can be proven first.
- Limitation type: Scope control.
- Detection: Local projection works and prep workflows become the next real bottleneck.
- Residual form: Remote server owns storage, auth, sync, backup, campaign organization, and optional AI cleanup; gateway remains responsible for live projection.

## spec:4 — Map Project Model And Privacy Layers

### spec:4.1 — Core Map Model

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

### spec:4.2 — Fog / Mask

Fog hides regions the players have not reached or cannot see.

Required controls:

- paint fog,
- rectangle/polygon/lasso fog,
- erase/reveal,
- save reveal state,
- undo/redo.

Relevant scout: [Scout 001](scout/scout-001-existing-battle-map-projection-solutions.md) found Mappadux's fog/MapFX controls worth inspecting for interaction patterns, while preserving this product's simpler distinction between fog/mask and Clean/Hide.

### spec:4.3 — Clean / Hide Pen

Clean removes DM-only marks inside otherwise visible space.

Use cases:

- room numbers,
- trap markers,
- secret door symbols,
- treasure labels,
- keyed object numbers,
- DM notes.

The tool should behave like a healing or inpainting brush and should avoid revealing that something was hidden.

### spec:4.4 — Auto-Clean

Auto-Clean is optional and should not block live play.

It may be used for prep or complex maps. Output should become proposed edit layers, not a replacement bitmap. The DM must be able to compare, accept, reject, restore, and manually adjust suggested changes.

**B6: AI cleanup is optional**

- Ideal: Player-invisible information disappears quickly and safely.
- Constraint: The first versions should not require AI API calls or internet access.
- Limitation type: Latency, reliability, and scope.
- Detection: Manual clean/hide is too slow or a remote/prep workflow exists where AI latency is acceptable.
- Residual form: AI cleanup becomes an optional prep feature and proposed edit layer.

## spec:5 — Capture, Normalization, And Display

### spec:5.1 — Capture And Normalization

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

### spec:5.2 — Display Modes

Map Mode projects the cleaned player-safe map image.

Outlines Mode projects high-contrast geometry for tracing, terrain placement, or low-clarity projection environments.

Outlines may begin with edge detection and manual cleanup before more advanced CV or AI generation.

## spec:6 — Calibration, Scale, And Projection Controls

### spec:6.1 — Calibration

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

Relevant scout: [Scout 001](scout/scout-001-existing-battle-map-projection-solutions.md) should inform source-map scale, true-table-scale rendering, and projector view controls. It does not solve the camera-to-projector-to-mat homography this section requires.

### spec:6.2 — Scale Rules

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

### spec:6.3 — Live Controls

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

**B7: Calibration automation must not block manual correction**

- Ideal: The gateway calibrates itself against the physical mat quickly and accurately.
- Constraint: Manual fallback is required because table conditions, camera quality, glare, shadows, and skew may break automatic detection.
- Limitation type: Physical environment.
- Detection: Grid detection and calibration succeed reliably across real table conditions.
- Residual form: Manual controls remain as useful override tools even after automation improves.

## spec:7 — MVP Exploration And Evidence

### spec:7.1 — MVP Direction

The MVP is not the product spec. It is the exploration path for proving the spec.

Early work should prove:

- source grid can be mapped to physical mat grid,
- a laptop-as-gateway plus projector plus fixed camera can support calibration,
- alignment can be corrected quickly by a DM,
- projection is useful enough for tracing or terrain placement,
- Map mode or Outlines mode has the stronger table value.

Relevant scout: [Scout 001](scout/scout-001-existing-battle-map-projection-solutions.md) is the first prior-art packet for Story 001. Before building projection/pairing from scratch, inspect whether Mappadux should be forked/adapted, used as reference only, or rejected for this product.

### spec:7.2 — Open Questions

- How large an encounter area can the projector cover from realistic table placement?
- How severe is focus falloff from a skewed projector angle?
- Can an iPhone remote camera provide stable enough frames for calibration before a dedicated webcam exists?
- What mini-computer hardware is required for calibration, projection, and image editing without live cloud AI?
- Which operations belong permanently on the local gateway, and which should move to an optional remote storage/auth server?
- What auth model is sufficient if prepared maps and reveal states sync remotely?
- How well does a cardboard, taped, or printed mount preserve camera/projector geometry?
- Is Map mode visually useful in real lighting, or is Outlines mode the main workflow?
- How accurate does calibration need to be before manual nudge is good enough?
- How fast can Clean/Hide work locally?
- When should cloud AI be part of prep, if ever?

### spec:7.3 — Deferred Methodology Lanes

The repo has no app code, runtime service, browser UI, eval harness, or hardware measurements yet. Runtime launchers, UI scouts, codebase-improvement scans, and automated evals should wait until those surfaces exist.
