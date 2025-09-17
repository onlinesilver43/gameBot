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
  - `hotkeys.py` — Global hotkeys (Ctrl+Alt+P Pause/Resume, Ctrl+Alt+O Kill) using `keyboard` or Win32 fallback.
- CLI Utilities (`bsbot/main.py` & scripts)
  - PowerShell scripts under `scripts/` bootstrap the venv, run the server, capture tests, and template extraction.

## Data & Config

- `assets/templates/` — Edge-detected templates (e.g., `wendigo.png`).
- `assets/images/` — Full screenshots for testing and template extraction.
- `config/profile.yml` — Default window title, ROI, delays, and detection thresholds.
- `config/keys.yml` — Key bindings for combat/interaction actions.
- `config/elements/` — Per-element detection hints (monsters, loot, etc.); monster profiles can include base word, optional prefix, and attack cues for variant targeting.

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
6. Sleep ~300 ms and repeat until paused or stopped.

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
