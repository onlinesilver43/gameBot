# Tasks

> Source of truth for active work items shared by Codex and Groc5fast.
>
> States: `todo`, `doing`, `review`, `done`
>
> Owners: `codex`, `groc5`

| id | title | owner | state | acceptance criteria |
|---|---|---|---|---|
| R0-1 | UI method toggle (Template/OCR) | codex | todo | UI shows method selector; `/api/start` accepts `method`; runtime honors method; status reflects method. |
| R0-2 | OCR dedup (NMS + size filter) | codex | todo | OCR multi boxes reduced on HUD; no IndexError; counts stable on screenshots and window. |
| R0-3 | Event timeline in UI | codex | todo | UI panel lists last 50 events (detections/actions) with timestamps; logs mirror. |
| R1-1 | Combat dry‑run click simulator | codex | todo | From detection, compute hitbox; visualize click target; no actual inputs; event timeline shows would‑click. |
| R1-2 | Input driver (safe) | groc5 | todo | Mouse move/click + keypress with min delay, jitter; foreground guard; dry‑run toggle. |
| R1-3 | Combat engage loop | groc5 | todo | After template hit, click hitbox; send attack; confirm via prompt/animation; retry up to N; cooldowns. |
| R1-4 | Loot pickup | groc5 | todo | Detect loot prompt/button; click; confirm pickup; cooldown. |
| R2-1 | Fishing node detection | codex | todo | Template/color anchors for fishing; interact loop with progress cue. |
| R2-2 | Woodcut node detection | groc5 | todo | Template/color anchors for trees; interact loop. |
| R3-1 | Local waypointing | codex | todo | Move between two screen-local waypoints using anchors; log path. |
| R4-1 | Inventory full + vendor | groc5 | todo | Detect full bag; vendor flow; resume route; safeguards. |

## Notes
- Keep tasks small and independently verifiable.
- Update `owner/state` and append validation steps when you pick up an item.
- Add links to artifacts under each row as we progress (e.g., previews, screenshots).
