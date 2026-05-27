# Assumptions And Risks

## Current Prototype Assumptions

- The first rig uses a generic laptop as a stand-in for the eventual local gateway.
- The likely finished home rig uses a Raspberry Pi or similar mini-computer, an off-the-shelf HDMI projector, and a cheap webcam.
- The camera is fixed to the projector with a temporary cardboard, taped, or printed mount so its position relative to the projector stays fixed.
- An iPhone remote camera is acceptable for early development before a dedicated webcam is available.
- The local gateway hosts the first web interface unless testing proves a separate server is needed.
- The gateway should display or expose a QR code so the DM can quickly open the local web interface.
- The first versions should avoid mandatory AI API calls and should work on local hardware where practical.
- Remote storage/auth is expected later for prep away from the projector, but it is optional and explicitly outside the MVP. Live projection should not require internet access.
- The projector may sit on the table or clamp near the table rather than mounting overhead.
- The battle mat has a visible 1-inch square grid.
- Manual calibration fallback is acceptable for the first proof.
- The first useful output may be a projected grid or outlines, not a polished map image.

## Key Risks

### Projection Coverage

The projector may not cover enough table area from a low side angle.

### Focus And Brightness

Skewed projection may produce uneven focus, dim corners, or glare.

### Camera Stability

iPhone remote camera behavior may introduce latency, exposure shifts, resolution limits, or connection friction. A dedicated webcam may become the more reliable calibration input.

### Hardware Sizing

The project needs a future hardware-requirements pass based on measured CPU/GPU needs, camera resolution, projection latency, local image operations, and whether any inpainting or cleanup work must run on the gateway.

### Remote Storage Boundary

Prepared-map storage is expected to belong on a remote authenticated server after the MVP, but adding that too early would slow the first physical proof. The data model should be sync-friendly without making sync mandatory.

### Calibration Error

Grid detection or homography may be technically correct but not accurate enough for physical play.

### Table Occlusion

Hands, minis, terrain, books, and shadows may interfere with camera calibration or projected visibility.

### Workflow Latency

The technical path may work but still take too long for live play.

## Proof Bias

Early stories should measure physical usefulness:

- seconds from start to usable projection,
- alignment error in inches or grid-square fractions,
- covered mat area,
- readability in room lighting,
- number of manual corrections needed.
