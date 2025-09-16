# Architecture

This project is a Windows screen‑automation bot for Brighter Shores. It is purely screen/IO based: no game memory reads. The runtime captures frames from the game window, detects on‑screen targets, decides what to do next, and simulates inputs with safety guards. A local web UI (port 8083) controls and observes the bot.

## High‑Level Components

- Capture & Windowing
  - `src/window.py` — Win32 helpers to find client rect, focus window, DPI awareness.
  - `src/capture.py` — `mss`-based client‑rect screen capture (returns BGR frames).
- Detection
  - `src/detect.py` — Hybrid detection:
    - Template matching (edge‑based) as primary for fixed UI words/icons.
    - OCR (Tesseract) fallback for robustness and template bootstrapping.
    - HSV color gates for red/teal UI text, non‑max suppression (NMS), OCR hardening.
  - `src/template_tools.py` — Heuristic template extractor from full screenshots (e.g., auto‑crop “Wendigo”).
- Runtime
  - `src/runtime.py` — Bot loop thread:
    - Computes ROI → capture → detect (template or OCR) → update status → produce preview overlay.
    - Tracks counters (`count`, `total_detections`), debuggable JSON `last_result`.
    - Future: state machine (Idle, Scan, Engage, Loot, Skill, Recover).
- Input
  - `src/input.py` — [planned] Mouse/keyboard simulation and humanized timing (rate limits, jitter, cooldowns).
- Control & Observability
  - `src/server.py` — Flask server (UI + API), serves:
    - `POST /api/start|pause|stop` — runtime control.
    - `GET /api/status` — snapshot with counts, boxes, method, confidence.
    - `GET /api/preview.jpg` — annotated ROI JPEG.
    - `GET /api/logs/tail` — rotating log tail.
    - `GET /api/diag` — dependency versions.
  - `src/hotkeys.py` — Global hotkeys (Ctrl+Alt+P pause/resume, Ctrl+Alt+O kill) via `keyboard` if present or Win32 `RegisterHotKey` fallback.
  - `src/logging_setup.py` — Rotating file (`logs/app.log`) + console logger.
- CLI utilities
  - `src/main.py` — Minimal runners for testing screenshot/window detection from the shell.

## Data & Config

- Assets
  - `assets/templates/` — Edge‑matching templates (e.g., `wendigo.png`).
  - `assets/images/` — Full screenshots for template extraction and tests.
- Config (planned)
  - Profiles: window title, ROIs per feature, delays, method preferences.
  - Keys: action bindings (attack, loot, interact, etc.).
  - Elements: detection params for monsters/loot/buttons.

## Detection Pipelines

- Template (Primary)
  - Preprocess: grayscale + Canny edges → `cv2.matchTemplate` (TM_CCOEFF_NORMED).
  - Threshold + NMS ⇒ zero or more boxes. Confidence = best match score.
  - Pros: fast, low false positives for fixed UI. Cons: sensitive to scale/visual changes.
- OCR (Fallback / Bootstrap)
  - Preprocess: HSV red mask → grayscale → upscale → Tesseract `image_to_data`.
  - Hardened parsing; optional NMS of word boxes. Confidence often near zero on stylized HUD text.
  - Pros: no templates required; Cons: slower, noisier.

## Runtime Loop (Current)

1. Find window client rect; compute central ROI (configurable).
2. Capture ROI; run template or OCR pipeline.
3. Draw overlays; encode JPEG; update `last_result` and counters.
4. Sleep 300 ms; repeat until paused/stopped.

## Safety & Controls

- Foreground focus checks (planned before sending input).
- Global hotkeys: pause/resume and kill.
- Panic via UI Stop.
- Rate‑limited actions (to be enforced in `input.py`).

## Extensibility

- New templates/images are just files + thresholds.
- Future YAML profiles to define ROIs, elements, keys without code changes.
- Behavior layer can evolve from a simple state machine to behavior trees.

---

## Open Technical Items

- ROI editor in UI (drag to set/save relative rects).
- Decision layer: Combat state machine, dry‑run click simulator.
- Input driver with humanized timing + cooldowns.
- Template scaling pyramid for small DPI drift.
- Per‑template stats and threshold auto‑suggest.
