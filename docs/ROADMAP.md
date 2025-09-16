# Roadmap

This roadmap focuses on shipping reliable, screen-only automation for Brighter Shores in small, testable increments.

## Phase 0 — Stabilization & UX (current)
- UI method toggle (Template vs OCR) and defaults per profile.
- OCR dedup: NMS + size/aspect filters to reduce noisy multi-boxes.
- ROI editor overlay (drag to set/save relative rects) — nice-to-have.
- Event timeline in UI (last 50 decisions/detections).
- Acceptance: No crashes, consistent template confidence when word visible, clear counts.

## Phase 1 — Combat MVP
- Detect target nameplate (e.g., Wendigo/Spriggan) via template; OCR fallback.
- Derive hitbox below nameplate; humanized click; attack key sequence.
- Confirmation: attack prompt/animation within T ms; retry up to N; cooldown.
- Loot pickup after combat; optional rarity filters later.
- Acceptance: 10 engagements ≥80% success, <5% false clicks.

## Phase 2 — Skilling MVP (Fishing, Woodcutting)
- Node detection via color anchors + templates.
- Interact → wait-for-progress cues → repeat; respawn re-scan.
- Anti-AFK randomness (micro-pauses, timing jitter).
- Acceptance: 15-minute loops with ≤2% wasted inputs and zero hard stalls.

## Phase 3 — Navigation (Local Waypoints)
- Detect landmarks/compass; screen-local stepping between points.
- Camera centering and adjustments as needed.
- Acceptance: 10 round trips between two waypoints with ≥90% success.

## Phase 4 — Inventory & Vendor
- Detect bag full; route to vendor; sell common items; confirm; resume.
- Whitelists and safeguards to prevent mis-sells.
- Acceptance: ≥90% successful sell cycles with zero protected-item sells.

## Phase 5 — Robustness & Scale
- Recovery states (stuck timers, retry strategies).
- Profile/element packs by area/episode; hot reload via UI.
- Per-template performance metrics and threshold auto-suggestion.

## Backlog / Nice-to-Have
- Behavior Tree/GOAP replacement for the state machine.
- Multi-target prioritization and black/white lists.
- Route planner for broader navigation.
- Remote control API (beyond localhost) with auth.

---

## Milestone Checklists

- Combat MVP
  - [ ] Template pack for target words and attack prompt
  - [ ] Hitbox calculation + click simulator (dry-run)
  - [ ] Attack cadence with cooldowns
  - [ ] Engage confirmation + retry logic
  - [ ] Loot template + pickup

- Skilling MVP
  - [ ] Fishing spot template + interact
  - [ ] Progress cue detection and loop
  - [ ] Respawn detection and re-scan pattern

- Navigation
  - [ ] Landmark templates
  - [ ] Stepwise movement + camera alignment

- Inventory & Vendor
  - [ ] Full-inventory detector
  - [ ] Vendor interaction flow
  - [ ] Resume path
