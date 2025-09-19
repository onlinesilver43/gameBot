# Combat Detection Strategy

This document captures the current OCR-first combat pipeline and the roadmap for the upcoming tile-aware enhancements. It is the primary reference for detection behaviour and should be updated whenever the combat controller changes.

## Current (R1) Behaviour

1. **Compass alignment & minimap anchor** – When `compass_auto_align` is enabled the runtime samples the compass ROI, calculates the needle angle, and issues left/right keypresses until the compass is North-up. Minimap auto-toggles every ~45 s to OCR the player’s absolute tile (`calibration|minimap_anchor` events update `/api/status.world_tile`).
2. **Frame capture** – The combat ROI is sampled once per loop (~100 ms). A `TileGrid` derived from `tile_size_px`, `tile_origin_px`, and `player_tile_offset` converts between screen pixels and tile indices.
3. **Nameplate detection & locking** – Template matching is attempted first, with OCR fallback. Prefix hits extend a 1.2 s lock window so slight occlusions retain the target. Combined prefix/nameplate boxes update `target_lock` telemetry and queued clicks.
4. **Tile tracker update** – The centre of the locked nameplate is projected into grid space. `TileTracker` maintains `(row, col, vx, vy)` with decay and emits `transition|tile_move` whenever the tracked tile changes. If the nameplate drops, predictions persist for ≤0.6 s.
5. **Hover gating** – When the tracked tile is adjacent to the player tile we enqueue a `hover_tile` action. Hover moves the cursor to the tile centre; a micro OCR pass over `TileGrid.hover_label_rect` must detect the floating **Attack** cue before any context button is considered. Timeline order: `hover_tile` → `detect|nameplate` (sustained) → floating OCR note.
6. **Context menu detection** – Once the hover is confirmed, `TileGrid.context_menu_rect` defines a strict ROI for menu OCR. `Attack`/`Info` boxes outside this rectangle are discarded, eliminating false positives from floating labels. Successful detections trigger `click|attack_button` and update `confidence_history.attack_button`.
7. **Telemetry & API surface** – `/api/status` now reports compass angle, last alignment timestamp, minimap anchor metadata, tracker world tile offsets, hover state, and planned actions. The UI timeline mirrors these events for debugging.

## Tile Workflow Reference

- **Compass normalisation** – Needle angles are sampled from `compass.roi`; positive offsets trigger the left rotation key, negative the right. `calibration|compass_align` events provide drift diagnostics.
- **Tile calibration helpers** – `TileGrid.from_samples` and `calibrate_tile_grid` convert between screen pixels and tiles. Unit tests guarantee <1 px error across 25 sample points.
- **Tracker telemetry** – `tile_tracker` status now contains `(row, col)`, velocity, hover confirmation, planned hover flag, and derived world tile (when the minimap anchor is known).
- **Hover confirmation** – `hover_tile` actions surface in the timeline with matching planned-click markers on the preview. Floating OCR confidence is reported in both telemetry and the hover section of `/api/status`.
- **Context ROI enforcement** – Attack/Info OCR runs strictly inside the context rectangle; rectangles are shown in magenta on the preview to aid tuning.
- **Attack template ROI defaults** – The default attack ROI is centred on the context menu band (`0.22, 0.10, 0.40, 0.24`), and calibration search bounds now cover the higher placement used by the redesigned HUD.
- **Minimap anchoring** – The minimap toggle key is configurable (`minimap.toggle_key`). Anchors update `world_tile` and timestamp telemetry, feeding future navigation work.

## Automatic Template ROI Calibration

- **Capture triggers** – When the nameplate or attack button template misses but OCR succeeds, the runtime captures the live combat frame and writes it to `logs/calibration/<timestamp>_{nameplate|attack}/`. Timeline entries are prefixed `CALIBRATING|detector|BEGIN` so you know calibration kicked off.
- **Background sweep** – A worker thread searches the captured frame for the optimal normalised ROI using the stored template image. Results are written alongside the capture (`calibration.json`) and surfaced as `CALIBRATING|detector|APPLY`, `…|NO_MATCH`, or `…|ERROR`, followed by a matching `…|END` marker.
- **Stable streaks** – Six consecutive template hits mark a detector as stable (`CALIBRATING|detector|STABLE`). While stable, the first OCR fallback is ignored and logged as `…|SKIP reason=stable_single_fallback`. The flag clears once the fallback streak reaches two consecutive misses, and the transition is logged as `CALIBRATING|detector|UNSTABLE`.
- **Smart gating** – Duplicate captures are skipped with `CALIBRATING|detector|SKIP` (notes include the reason). Even without overrides the manager now waits for two consecutive fallbacks and a 30 s gap since the last good template hit before scheduling a sweep. This keeps calibrated ROIs steady when scores hover around 0.95.
- **Overrides** – Successful runs (score ≥ 0.90, or ≥ 0.88 for the first override) update `config/calibration/roi_overrides.yml`. Controllers consume these overrides on the next frame, so template matching reuses the calibrated window automatically. `/api/status.calibration` exposes the current ROI, success streaks, stable flags, and last capture folder.
- **Manual management** – Each calibration lives in its own timestamped folder; delete any directory under `logs/calibration/` to discard that run. The system will regenerate a new capture if OCR falls back again.

## Validation Checklist

- Rotate the camera ±180°: timeline should record `calibration|compass_align` events, and `/api/status.compass.angle` should settle within ±5°.
- Run `python -m unittest tests.test_tracking_tile` to confirm tile calibration accuracy (<1 px error).
- Simulate diagonal movement: tracker timeline must emit ordered `transition|tile_move` entries without jumps.
- Observe a dry-run encounter: timeline must show `hover_tile` followed by floating OCR before `click|attack_button`.
- Confirm `/api/status` includes `world_tile`, hover state, compass block, and `last_result.tile_tracker` fields for each sampled frame.
