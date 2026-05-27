# Scout 001 - Existing Battle Map Projection Solutions

**Source / Question:** Has somebody already built the RPG Map Projector product, or enough of it that we should copy, fork, or adapt it?
**Scouted:** 2026-05-27
**Scope:** Public tools for in-person tabletop map projection, projector/player views, fog of war, true-table-scale rendering, local web control, and camera/projector calibration.
**Status:** Filed

## Executive Recommendation

Spike Mappadux / Dynamic Map Renderer v2 before writing our own projection and pairing stack.

It is the closest existing open-source project found. It already covers local web/PWA operation, QR or room-code joining, peer-to-peer player/projector views, uploaded image maps, fog/painted masks, map packs, and true-table-scale projector rendering. Its MIT license makes code reuse legally plausible.

Do not adopt it wholesale yet. Mappadux is still a VTT-at-home map renderer, not the exact product described by our Ideal/spec. The distinctive gaps for us remain physical battle-mat calibration through a fixed camera/projector rig, automatic or assisted alignment to the real mat, photo/PDF module-map capture and de-skew, and player-safe cleanup of room numbers/traps/secret labels.

## Evidence

- [Mappadux / Dynamic Map Renderer v2](https://github.com/FrunkQ/dynamic-map-renderer-v2) is the strongest lead. The README describes no account, no application server, browser-local storage, LAN second-screen pairing by QR, PeerJS-based real-time sync, image upload/library, fog/MapFX, and scaled battlemap projection at true table scale. The hosted app is [mappadux.com](https://www.mappadux.com/).
- Local code inspection of Mappadux at `cd5c1e8` (`2026-05-26`, package version `2.16.0`) found a Vite/TypeScript/Three.js app with `peerjs`, `qrcode`, IndexedDB storage, PWA support, projector and calibration entry points, and tests. The repo has an [MIT license](https://raw.githubusercontent.com/FrunkQ/dynamic-map-renderer-v2/main/LICENSE).
- Mappadux's projector calibration is display-scale based, not camera-based. `src/projector/calibrationStorage.ts` stores CSS pixels per physical 1-inch/25-mm square, and `src/viewers/strategies/computeView.ts` computes the projected crop from map pixels-per-square divided by projector pixels-per-square. That is useful reference code for source-map scale and table-scale rendering, but it does not appear to compute a projector-to-camera-to-mat homography.
- Mappadux's map calibration is manual/image-internal: a DM identifies map scale/grid origin in the image. It is relevant to our source-grid controls, but it does not solve capturing a photographed module map, de-skewing it, removing DM-only symbols, or aligning the projection against a live camera frame of the physical mat.
- [Table Slayer](https://tableslayer.com/) is another close adjacent product: an in-person TV battlemap web app with GM controls, fog of war, weather, and a suggested Raspberry Pi / mini-PC display setup. Its [GitHub repo](https://github.com/Siege-Perilous/tableslayer) is source-available under a Functional Source License that restricts competing use until the future Apache grant, so it is a weaker copy/modify target for us.
- [Dungeon Revealer](https://github.com/dungeon-revealer/dungeon-revealer) is open source and self-hosted. It supports uploading a map, DM/player pages, fog reveal, map library, local-network use, and optional DM/player passwords. It is useful prior art for a simple local server and reveal workflow, but it is not focused on calibrated physical projection.
- [Dungeon Map Cast](https://netox.itch.io/dungeon-map-cast), [Arkenforge](https://arkenforge.com/), [Dynamic Dungeons](https://dynamicdungeons.com/), [RPG Map](https://rpgmap.app/), [RollBerry/MapBerry](https://rollberry.de/en/), and [Dungeon View](https://dungeonview.com/products/dungeon-view%E2%84%A2-tabletop-map-projector) all cover parts of the in-person map/display space: projector or TV display, fog, tokens/markers, map grids, imports, or packaged hardware. None of the checked product pages show the combined workflow we want: module-map capture -> normalize/de-skew -> hide DM-only marks -> camera-assisted projection alignment onto a real gridded mat.
- Outside the TTRPG product space, camera-based projector calibration is a solved projection-mapping pattern. [OmniCal](https://origin.disguise.one/en/products/omnical/) is a commercial example using cameras and structured light to calibrate projectors to physical surfaces. That supports treating our camera/projector alignment as feasible component work, not as evidence that a hobby RPG product already exists.

## Adoption Decision

- Decision: Spike
- Why: Mappadux is close enough to change our build path, but not close enough to replace the product. It can answer whether we should fork/adapt an existing TypeScript web/PWA projector stack or only borrow specific concepts.
- Follow-up owner: Story 001 now includes a short Mappadux spike before first-principles implementation. If the spike recommends forking or building on Mappadux architecture, create an ADR before committing the project to that base.

## Product Fit

- Ideal refs: Product Identity, Physical Table First, Calibration Is Product Core, Player-Safe Projection
- Spec refs: `spec:1`, `spec:2`, `spec:3`, `spec:4`, `spec:5`, `spec:6`, `spec:7`
- Story refs: `story-001-calibration-projection-spike`
- ADR refs: None yet. Create one only if choosing fork/adopt/base-architecture rather than concept borrowing.

## Risks And Open Questions

- Mappadux may pull the project toward full VTT features: tokens, audio, dynamic lighting/effects, handouts, and map packs. Our product should resist that unless a feature directly accelerates physical module-map-to-mat projection.
- Mappadux's PeerJS path may rely on a public broker for cross-device signaling unless self-hosted. For our local gateway, QR pairing and same-LAN control should be designed so live play is not dependent on an external service.
- Its true-table-scale approach assumes a calibrated display/projector window, not a live camera feedback loop. We still need our own proof for camera frame capture, physical mat grid detection or manual point marking, projection transform, and latency.
- Licensing is favorable for Mappadux but not equally favorable across adjacent tools. Table Slayer should be treated as reference/prior art, not a code source, unless its license position is reviewed.
- No exact solved product was found in this scout pass. The next scout should be narrower if Story 001 confirms the hard part is projector-camera calibration: OpenCV/browser CV options, ArUco/AprilTag markers, homography estimation, camera input on the target gateway, and projector latency.
