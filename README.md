Brighter Shores Bot — Build & Run Guide

Overview
- Windows‑focused computer vision bot with UI server.
- Detects targets via Template or OCR (Tesseract) with live preview.
- Scripts provided for setup, serving UI, testing, and template extraction.

Prerequisites (Windows)
- Python 3.11 (installed via the `py` launcher).
- PowerShell (run scripts from a normal or admin prompt).
- Tesseract OCR (optional for OCR mode): Install to `C:\\Program Files\\Tesseract-OCR` or know your `tesseract.exe` path.
- GPU not required.

Quick Start
1) Setup environment and deps
   - PowerShell: `scripts\\setup.ps1`
   - Options:
     - `-PythonVersion 3.11` to pick Python version.
     - `-TesseractPath "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"` to set OCR path.
     - `-AddTesseractToPath` to add Tesseract folder to user PATH.

2) Run the UI server
   - PowerShell: `scripts\\serve.ps1`
   - Options:
     - `-Port 8083` (default).
     - `-LogLevel INFO|DEBUG|WARNING|ERROR|CRITICAL`.
     - `-TesseractPath <path\\to\\tesseract.exe>` to override per run.
   - Open `http://127.0.0.1:8083` in your browser.

3) Start detection from the UI
   - Title: exact window title (default: `Brighter Shores`).
   - Word: OCR target (default: `Wendigo`).
   - Template Path: optional PNG for template matching (e.g. `assets\\templates\\wendigo.png`).
   - Tesseract Path: optional `tesseract.exe` path if not on PATH.
   - Method: `auto`, `template`, or `ocr`.

Diagnostics
- API: `GET /api/diag` shows versions of OpenCV, NumPy, MSS, Flask, and Tesseract availability.
- Logs: tail UI via `GET /api/logs/tail?n=200` or see files under `logs\\`.

Utilities (PowerShell)
- Test capture + detection on live window ROI:
  - `scripts\\test-window.ps1 -Title "Brighter Shores" -Template assets\\templates\\wendigo.png`
  - Without template, OCR is used: `scripts\\test-window.ps1 -Word Wendigo -TesseractPath "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"`
  - Outputs: `window_roi.detected.png` (success) or `window_roi.png` (for debugging).

- Extract a template from a screenshot using red‑text heuristics:
  - `scripts\\extract-template.ps1 -Screenshot assets\\screenshots\\sample.png -Template assets\\templates\\wendigo.png`

Configuration
- Optional YAML config lives under `config\\` and is surfaced in UI status.
- Loader stubs: `bsbot.core.config.load_profile()` and `load_keys()`; safe to run without files present.

Hotkeys (global)
- Ctrl+Alt+P: pause/resume runtime
- Ctrl+Alt+O: kill process

Notes & Limitations
- Windows only: window discovery and capture use Win32 APIs (`ctypes`) and `mss`.
- WSL is not supported for runtime capture; run from Windows PowerShell.
- OCR requires Tesseract; template mode does not.

Troubleshooting
- Window not found: verify the exact window title and that the game is running.
- No OCR results: ensure Tesseract is installed; provide `-TesseractPath` or set `TESSERACT_PATH` env var.
- Black preview or zero boxes: confirm the game window is not minimized and that the ROI is correct.
- Import errors: re‑run `scripts\\setup.ps1` to recreate venv and reinstall requirements.

Repository Structure (key bits)
- `bsbot/` — main package
  - `ui/server.py` — Flask server for the UI
  - `runtime/service.py` — capture + detection loop
  - `vision/` — OCR and template detection
  - `platform/` — Win32 window utilities and screen capture
- `scripts/` — PowerShell helpers (`setup.ps1`, `serve.ps1`, `test-window.ps1`, `extract-template.ps1`)
- `assets/` — templates and screenshots (optional)
- `config/` — optional YAML configuration
- `logs/` — runtime logs
