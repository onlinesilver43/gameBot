# Decisions Log

A lightweight log of key technical/product decisions. Append new entries at the top.

## 2025-09-16 — Detection Strategy and Controls
- Decision: Use edge-based template matching as primary for fixed UI words (e.g., Wendigo), OCR as fallback.
- Reason: Higher precision and meaningful confidence with fixed scale; OCR is noisy for HUD fonts.
- Consequences: Maintain template packs and a quick template-extractor; add small scale tolerance.
- Also: Global hotkeys (Ctrl+Alt+P pause/resume, Ctrl+Alt+O kill) are mandatory and must remain available.

## 2025-09-16 — Web UI and Port
- Decision: Serve the local control UI via Flask on 8083.
- Reason: Simple local hosting; fast iteration; embeddable status/preview/logs.
- Consequences: Keep endpoints stable; expand UI incrementally (method toggle, timeline, ROI editor).
