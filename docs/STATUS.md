# Current Status

Updated: now

## Summary
- UI server (port 8083) runs with Start/Pause/Stop and global hotkeys.
- Detection works via Template (preferred) and OCR (fallback/bootstrapping).
- Live status shows per-frame `count`, `boxes`, best `confidence`, and `total_detections`.
- Logs stream to `logs/app.log` and the UI tail.

## What Works
- Window detection + client-rect capture with ROI.
- Template extraction from full screenshots (e.g., Wendigo) and template detection with NMS.
- OCR with red-mask prefilter and hardened parsing (less crashy, still noisy for HUD fonts).
- UI control + preview overlays + diagnostics endpoint.
- Hotkeys: Ctrl+Alt+P pause/resume, Ctrl+Alt+O kill.

## Known Issues / Gaps
- OCR produces multiple low-confidence word boxes for stylized HUD text; counts can be noisy.
- No input driver yet; Combat MVP not clicking/attacking (by design, pending dry-run validation).
- ROI is static; needs UI editor to tune in-app.
- No YAML profiles/keys yet; parameters live in code/UI fields.

## Next Actions (Short Term)
- Add UI method toggle (Template/OCR) and remember last choice.
- Implement OCR NMS and size/aspect gates to reduce duplicates.
- Add event timeline in UI and a dry-run click simulator for Combat MVP.
- Implement input driver with humanized timing (safe but responsive).

## How To Run (recap)
- Setup: `scripts\\setup.ps1 -TesseractPath "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"`
- Serve UI: `scripts\\serve.ps1 -Port 8083 -LogLevel DEBUG`
- In UI: set Template `assets\\templates\\wendigo.png` and Start.

## Metrics Targets
- Detection precision/recall ≥95% in tuned ROIs for primary templates.
- Action latency <250 ms after confirmed detection.
- Stable runtime 2+ hours without crash or runaway actions.

## Recent Fixes
- Hardened OCR confidence/bbox parsing (avoid `IndexError`).
- Template read failure now falls back to OCR with warning, avoiding loop crashes.
- Hotkeys reworked to Win32 fallback to avoid dependency and admin requirements.
