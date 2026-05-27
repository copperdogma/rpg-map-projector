# Inbox

## Raw Follow-Up Items

- Determine hardware requirements once the prototype clarifies what the gateway must do: projector output, webcam input, calibration loop, image normalization, mask compositing, possible local cleanup/inpainting, hosting the DM web UI, and offline operation.
- Add QR-code pairing so the projector/gateway can show a local URL that the DM opens from a phone or iPad.
- Keep the first version local-first, with the Raspberry Pi or mini-computer hosting the web interface directly.
- Design the data model so a future remote storage/auth server can support prep away from the projector: capture maps, process them, name/save them, sync them, then send them to the gateway when it is online.
- Maintain a list of operations that might move to a remote server later, such as account storage, sync, prepared map libraries, campaign organization, backups, optional AI cleanup, and cross-device continuity.
- Keep native iOS as a later option after the web interface proves the workflow; the first version should be a web page to reduce setup and distribution friction.

Use this file for raw follow-up ideas, constraints, hardware notes, and playtest observations before sorting them into Ideal, spec, assumptions, or stories.
