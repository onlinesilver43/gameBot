# Combat Detection Strategy

This document captures the current OCR-first combat pipeline and the roadmap for the upcoming tile-aware enhancements. It is the primary reference for detection behaviour and should be updated whenever the combat controller changes.

## Current (R1) Behaviour

1. **Single frame capture** – The runtime grabs the configured ROI once per loop (~100 ms cadence).
2. **Global OCR pass** – `detect_word_ocr_multi` searches the frame for the monster word and attack cues. Prefix filtering (“Twisted”) gates the nameplate before a lock is established.
3. **ROI refinement** – When the global pass reports a low-confidence match, we immediately re-run OCR on a cached ROI (2–2.5× upsampled, CLAHE + bilateral filter) to stabilise the prefix and base word.
4. **Candidate vs. confirmed events** – If only the base word is visible we emit `detect|nameplate_candidate`. Once both word and prefix clear the threshold we emit `detect|nameplate` and set the lock grace timer (~1.2 s).
5. **Attack button detection** – OCR runs inside the HUD band on the right-hand side. Planned clicks are only scheduled once both the nameplate and button are present; repeated clicks continue until the button disappears or the next phase triggers.
6. **Telemetry** – `/api/status` exposes `target_lock`, `click_attempts`, `confidence_history`, and `nameplate_candidate` information. The timeline mirrors these events with rich `notes` to aid debugging.

## Tile & Hover Roadmap

To stay competitive when monsters (and players) move, we are adding a tile-aware layer on top of the OCR foundation.

1. **Compass normalisation**
   - Automatically rotate the camera until the compass points North.
   - Watch for drift; if rotation changes, pause detection, re-align, and resume.

2. **Screen tile calibration**
   - Compute `screen_to_tile`/`tile_to_screen` helpers using the square grid.
   - Cache tile size/origin so all detections can be projected into the grid.

3. **Monster tile tracker**
   - Maintain a per-monster track `(row, col, vx, vy)` constrained to Chebyshev neighbours (including diagonals).
   - Predict the next tile when the nameplate momentarily disappears; retain ROI context to avoid re-scanning the entire frame.

4. **Hover confirmation workflow**
   - When a track enters an adjacent tile, move the cursor over that tile to reveal the floating **Attack** label.
   - Run a micro OCR pass over a small hover ROI; only after confirmation do we proceed to the context-menu button.

5. **Context button ROI**
   - Detect `Attack`/`Info` (and later `Prepare`, `Special`, etc.) within a fixed ROI anchored to the hovered tile.
   - This prevents false positives from the floating label and keeps click targets consistent.

6. **Minimap anchoring**
   - When the compass is clicked, the minimap reveals our absolute tile coordinates.
   - Capture those coordinates, map them to the world grid, then close the minimap and resume detection. This enables navigation between static interactables and across regions.

7. **Telemetry & documentation updates**
   - Surface tracker state (`tile`, velocity, predicted move) via `/api/status` and the timeline.
   - Keep `docs/ARCHITECTURE.md`, `docs/DETECTION.md`, and `docs/OPERATIONS.md` aligned as each milestone lands (see `docs/TASKS.md` entries R1-5 through R1-11).

## Validation Checklist

- Verify compass normalisation by rotating the camera ±180° and confirming the runtime re-aligns automatically.
- Ensure tile projection maps at least 10 sample grid intersections with <1 px error.
- Simulate a monster moving across the eight neighbouring tiles; the tracker timeline should show `tile_move` entries without jumps.
- During combat, confirm the floating **Attack** cue appears before the context-menu click.
- Confirm `/api/status` reports `nameplate_candidate`, `target_lock`, and tracker fields for each frame where the monster is visible.

Refer to `docs/TASKS.md` for ownership and acceptance criteria on each milestone.
