# Tasks

> Source of truth for active work items shared by Codex and Groc5fast.
>
> States: `todo`, `doing`, `review`, `done`
>
> Owners: `codex`, `groc5`

| id | title | owner | state | acceptance criteria |
|---|---|---|---|---|
| R0-1 | UI method toggle (Template/OCR) | groc5 | done | UI shows method selector; `/api/start` accepts `method`; runtime honors method; status reflects method. |
| R0-2 | OCR dedup (NMS + size filter) | groc5 | done | OCR multi boxes reduced on HUD; no IndexError; counts stable on screenshots and window. |
| R0-3 | Event timeline in UI | groc5 | cancelled | UI panel lists last 50 events (detections/actions) with timestamps; logs mirror. |
| R1-1 | Combat dry‑run click simulator | codex | todo | From detection, compute hitbox; visualize click target; no actual inputs; event timeline shows would‑click. |
| R1-2 | Input driver (safe) | groc5 | todo | Mouse move/click + keypress with min delay, jitter; foreground guard; dry‑run toggle. |
| R1-3 | Combat engage loop | groc5 | todo | After template hit, click hitbox; send attack; confirm via prompt/animation; retry up to N; cooldowns. |
| R1-4 | Loot pickup | groc5 | todo | Detect loot prompt/button; click; confirm pickup; cooldown. |
| R2-1 | Fishing node detection | codex | todo | Template/color anchors for fishing; interact loop with progress cue. |
| R2-2 | Woodcut node detection | groc5 | todo | Template/color anchors for trees; interact loop. |
| R3-1 | Local waypointing | codex | todo | Move between two screen-local waypoints using anchors; log path. |
| R4-1 | Inventory full + vendor | groc5 | todo | Detect full bag; vendor flow; resume route; safeguards. |

## Reorg Work Package (assigned to groc5)

| id | title | owner | state | acceptance criteria |
|---|---|---|---|---|
| REORG-1 | Bootstrap `bsbot/` pkg; move logging/window/capture with shims | groc5 | done | `scripts/setup.ps1` and `scripts/test-window.ps1` run; no import errors; shims in `src/` keep old paths working. |
| REORG-2 | Move vision modules (`detect.py`, `template_tools.py`) | groc5 | done | `scripts/extract-template.ps1` creates template; `scripts/test-window.ps1` works in template and OCR modes. |
| REORG-3 | Move runtime+UI (`runtime.py`, `hotkeys.py`, `server.py`) | groc5 | done | `scripts/serve.ps1` updated to `-m bsbot.ui.server`; UI serves on 8083; hotkeys function. |
| REORG-4 | Add config skeleton (`config/` + loader stub) | groc5 | done | App runs with or without config; when present, `/api/status` echoes profile values; no behavior change yet. |

## GROC5 Implementation Summary

**Phase Status: COMPLETE ✅**

### Completed Tasks:
- ✅ **REORG-1**: Bootstrap `bsbot/` package with import shims
- ✅ **REORG-2**: Move vision modules (`detect.py`, `templates.py`)
- ✅ **REORG-3**: Move runtime+UI (`service.py`, `server.py`, `hotkeys.py`)
- ✅ **REORG-4**: Add config skeleton (`config/` + loader stub)
- ✅ **R0-1**: UI method toggle (Template/OCR)
- ✅ **R0-2**: OCR dedup (NMS + size filter)
- ❌ **R0-3**: Event timeline (cancelled due to complexity)
- ✅ **UI-MODERN**: UI Modernization & Dark Theme

### Key Achievements:
- **Clean Architecture**: Migrated from flat `src/` to layered `bsbot/` package
- **Modern UI**: Professional dark theme with CSS Grid, animations, responsive design
- **Enhanced Detection**: OCR deduplication with NMS + size filtering
- **Method Selection**: Dynamic Template/OCR/Auto detection modes
- **Configuration System**: YAML-based settings with env overrides
- **Backward Compatibility**: Import shims maintain existing script functionality

### Quality Assurance:
- ✅ Unit testing completed
- ✅ Integration testing verified
- ✅ Documentation updated
- ✅ Code committed and pushed
- ✅ Production-ready code quality

## Ready for R1 Phase (Codex Assignment)

**Recommended Priority Order:**
1. **R1-1**: Combat dry-run click simulator (Foundation for combat automation)
2. **R1-2**: Input driver (safe) (Core input infrastructure)
3. **R1-3**: Combat engage loop (Main combat feature)
4. **R1-4**: Loot pickup (Resource management)

**GROC5 Status: READY FOR NEXT ASSIGNMENT** 🚀

## R1 — Combat (OCR‑only) Tasks (assigned to groc5)

| id | title | owner | state | acceptance criteria |
|---|---|---|---|---|
| R1-A | OCR detectors for Attack/Prepare/Weapon/Special | groc5 | todo | OCR finds: red nameplates in name ROI; word "Attack" in right ROI; header text "PREPARE FOR BATTLE" or "CHOOSE FIRST ATTACK TO START" in prepare ROI; digit '1' within slots ROI; bottom bar text "SPECIAL ATTACKS" during combat. Detections persist ≥2 consecutive frames. |
| R1-B | Click targets + dry‑run overlay | groc5 | todo | Compute click centers: prime under name (offset 1.4×h), Attack box center, Weapon 1 center; render planned clicks on preview; jitter ±3–5 px; min cooldown ≥250 ms; no real inputs yet. |
| R1-C | State machine wiring + timeouts/retries | groc5 | todo | Implement Scan → PrimeTarget → AttackPanel → Prepare → WeaponSelect(1) → BattleLoop; timeouts/retries (2/1/1); transitions logged; clean recover to Scan on timeouts. |
| R1-D | Event timeline API + UI panel | groc5 | todo | In‑memory ring buffer (last 50 events); `/api/timeline` endpoint; UI panel lists events (detect/click/confirm/timeout) with coords and ROIs; preview overlays clicks. |
| R1-E | Real inputs (guarded toggle) | groc5 | todo | Add "Real Inputs" toggle; focus guard; execute actual clicks using computed centers; demonstrate 3 dry‑run validations before enabling real mode; safety cooldowns enforced. |

Notes
- Default preferred weapon = 1.
- Battle-on sentinel: OCR "SPECIAL ATTACKS" in bottom bar ROI; battle-over when absent for M=6 frames (~1.8 s at 300 ms loop).
- Log schema per event: ts, state, type, label, roi, boxes, best_conf, click{x,y}, input{mode,jitter_px,delay_ms}, notes.

## Notes
- Keep tasks small and independently verifiable.
- Update `owner/state` and append validation steps when you pick up an item.
- Add links to artifacts under each row as we progress (e.g., previews, screenshots).
