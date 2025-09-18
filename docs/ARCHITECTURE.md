# Architecture

The Brighter Shores bot is a Windows-only, screen-driven automation framework. The runtime captures frames from the game window, routes each frame through a skill-specific controller (combat, fishing, etc.), and optionally issues human-like inputs with built-in safety guards. A local web UI on port 8083 orchestrates and observes the active skill.

## High-Level Components

- Platform & IO (`bsbot/platform/`)
  - `win32/window.py` — Win32 helpers for window discovery, focus, cursor position, DPI.
  - `platform/capture.py` — `mss`-based screen capture returning BGR frames for a given rect.
  - `platform/input.py` — Human-like mouse click helper with jitter, cooldowns, and foreground checks.
- Vision (`bsbot/vision/`)
  - `detect.py` — OCR + template primitives with NMS filtering and hitbox helpers.
  - `templates.py` — Utilities to extract and persist template images from screenshots.
- Skills (`bsbot/skills/`)
  - `base.py` — `SkillController` contract and `FrameContext` metadata.
  - `combat/controller.py` — OCR-first combat state machine (nameplate → attack → prepare → weapon → loop).
  - Additional skills plug in by subclassing `SkillController`.
- Runtime (`bsbot/runtime/service.py`)
  - `DetectorRuntime` thread owns capture loop, status JSON, timeline logging, and delegates frames to the active skill controller.
  - Maintains shared event/timeline buffer and manages live vs. dry-run click mode.
- Control & Observability (`bsbot/ui/`)
  - `server.py` — Flask server exposing `/api/start|pause|stop`, `/api/status`, `/api/preview.jpg`, diagnostics, and timeline endpoints.
  - `templates/index.html` — Modern UI with configuration form, live preview, logs, timeline, and click-mode selector.
    - Phase tracker badge mirrors the combat controller’s human-readable phase list, and both the timeline and activity logs highlight those labels alongside the raw FSM state for quick scanning.
  - `hotkeys.py` — Global hotkeys (Ctrl+Alt+P Pause/Resume, Ctrl+Alt+O Kill) using `keyboard` or Win32 fallback.
- CLI Utilities (`bsbot/main.py` & scripts)
  - PowerShell scripts under `scripts/` bootstrap the venv, run the server, capture tests, and template extraction.

## Data & Config

- `assets/templates/` — Edge-detected templates (e.g., `wendigo.png`).
- `assets/images/` — Full screenshots for testing and template extraction.
- `config/profile.yml` — Default window title, ROI, delays, detection thresholds, and global defaults.
- `config/keys.yml` — Key bindings for combat/interaction actions.
- `config/monsters/` — One YAML per creature (word, prefix, template, attack cues).
- `config/interfaces/` — UI interface definitions (attack button, prepare targets, weapon slots).
- `config/elements/` — Legacy element hints (loot, misc.).

## Detection Pipelines

- **Template (Primary for stable UI tokens)**
  - Grayscale + Canny edges → `cv2.matchTemplate` (TM_CCOEFF_NORMED).
  - Thresholded results deduplicated with NMS.
  - Strength: precise when the UI asset is consistent.
- **OCR (Primary for text, fallback when templates miss)**
  - Red-mask pass for enemy nameplates, grayscale fallback for white-on-dark buttons.
  - Uses `pytesseract.image_to_data`, filters by size/aspect, applies NMS.
  - Strength: no template required, works across variants.

## Runtime Loop

1. Acquire game window rect; compute skill-configured ROI.
2. Capture ROI via `bsbot.platform.capture.grab_rect`.
3. Build a `FrameContext` and dispatch to the active `SkillController` (combat by default).
4. Skill returns detection result JSON and an annotated preview.
5. Runtime updates shared status, logs timeline events, and, when in live mode, plays back scheduled human-like clicks.
6. Sleep ~100 ms by default (configurable via `BSBOT_LOOP_SLEEP`) and repeat until paused or stopped.

### State Machines & Events

- `CombatController` implements a six-state FSM that mirrors the combat sequence:
  1. **Scan** — “Search for Monster”. Emit `detect|nameplate` and (if configured) `detect|name_prefix` when OCR sees the target words.
  2. **PrimeTarget** — “Click on the Monster”. When ready, we emit `click|prime_nameplate` (dry-run or live) and await the attack button.
  3. **AttackPanel** — “Detect the Attack Box” / “Click the Attack Box”. Events `detect|attack_button` and `click|attack_button` fire here.
  4. **Prepare** — “Detect the Prepare for Battle box”. Emits `detect|prepare_header` while monitoring for the weapon slot.
  5. **Weapon** — “Detect/Click the Weapon box”. Events `detect|weapon_slot_1` and `click|weapon_1` advance the FSM.
  6. **BattleLoop** — “Detect fight started/completed”. Confirmation `confirm|special_attacks` signals the fight is active; absence of those cues triggers `transition|battle_end` and returns to Scan.

- Event types the runtime records:
  - `detect` — raw detections (`nameplate`, `name_prefix`, `attack_button`, `prepare_header`, `weapon_slot_1`).
  - `confirm` — secondary confirmations (`special_attacks`).
  - `click` — scheduled or executed clicks (`prime_nameplate`, `attack_button`, `weapon_1`).
  - `transition` — FSM transitions (`Scan->PrimeTarget`, `battle_end`, etc.).

### Activity Logs & Timeline

- **Activity Logs** (`/api/logs/tail`) mirror the logger output: detection summaries (`detect | found=True ...`), click cooldown skips, and transition notes. They provide the narrative context behind the raw events.
- **Event Timeline** (`/api/timeline`) streams the structured events listed above. Each entry includes timestamp, FSM state, event type, cue label, confidence, and any click coordinates.
- Together they trace every phase of the combat sequence: Scan emits nameplate/name_prefix, PrimeTarget adds click events, AttackPanel/Prepare/Weapon show the subsequent detections and clicks, and BattleLoop ends with a `transition|battle_end` when cues disappear.

### Development Patterns (R1 Focus)

- Canonical phases
  - The combat controller maintains human‑readable phase labels (e.g., "Search for Monster", "Click on the Monster").
  - Each event carries both the raw FSM `state` and the human‑readable `phase`. The status API also exposes `phase` for the UI badge.

- Current scope (enabled detections)
  - Nameplate and Attack are active. Prepare/Weapon/Special phases are intentionally suppressed until implemented; no events are emitted for them.
  - OCR‑only operation is supported; template mode can be enabled per profile but is not required.

- Variant gating and merged nameplate
  - When a `prefix_word` is configured (e.g., "Twisted") and the main `word` (e.g., "Wendigo"), the controller requires both tokens before treating the target as ready.
  - When both tokens are detected, their OCR boxes are merged into a single consolidated nameplate box and emitted as `detect|nameplate` (no separate `name_prefix` event). That box is cached with a 1.2s lock grace so the bot can continue operating if the prefix vanishes when the context menu appears.

- Confirm-then-advance pattern
  - PrimeTarget: re-click the nameplate at a safe cooldown while the nameplate persists and the Attack button is not yet visible.
  - AttackPanel: after clicking, keep re-clicking the Attack button (cooldown) while it remains visible; only advance once it disappears or the next cue is confirmed. Click attempt counters reset when a scan cycle restarts.
  - This pattern will be applied to downstream phases (Prepare → Weapon → BattleLoop) when they are enabled.

- UI & timeline semantics
  - The UI shows a live phase badge from `/api/status.phase` and highlights `phase=` in the Activity Logs. Timeline lines include the human-readable `phase` when available.
  - Transition events now carry `notes` (e.g., why we bailed from a phase), and `/api/status.last_result` surfaces breadcrumbs: `target_lock` (active/remaining), `click_attempts`, `confidence_history`, and the most recent `transition_reason`.

## Safety & Controls

- Foreground checks before issuing live clicks; cooldowns and jitter emulate human input.
- Global hotkeys (Ctrl+Alt+P/Ctrl+Alt+O) provide immediate pause/kill.
- `/api/stop` plus UI panic button stop the loop.
- Click-mode selector allows dry-run validation before enabling live interactions.

## Extensibility

- Register new skills by subclassing `SkillController` and calling `DetectorRuntime.register_skill()`.
- Shared OCR/template primitives keep detection logic DRY across skills.
- Input helpers live in one place (`platform/input.py`) so all skills inherit consistent safety behavior.
- Config and UI can surface skill-specific parameters without altering the runtime thread.

## Open Technical Items

- UI ROI editor for interactive capture tuning.
- Additional skills (fishing, woodcutting) built on the new controller framework.
- Expanded input driver (keyboard combos, drag/hold actions).
- Adaptive template scaling for DPI drift.
- Telemetry for per-template confidence trends and auto-threshold suggestions.
