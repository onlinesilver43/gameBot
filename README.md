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
   - Monster Profile: id from `config/monsters/` (e.g., `twisted_wendigo`).
   - Word: OCR target override (profile default used when empty).
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
- Monster profiles live under `config/monsters/`, interface profiles under `config/interfaces/`.
- Template and Tesseract defaults live in `config/profile.yml` (UI is read-only for these values).

Hotkeys (global)
- Ctrl+Alt+P: pause/resume runtime
- Ctrl+Alt+O: kill process

Notes & Limitations
- Windows only: window discovery and capture use Win32 APIs (`ctypes`) and `mss`.
- WSL is not supported for runtime capture; run from Windows PowerShell.
- OCR requires Tesseract; template mode does not.

## Troubleshooting

### 🚨 Quick Diagnosis

#### Check System Status
```bash
# Run diagnostics
curl http://127.0.0.1:8083/api/diag

# Check recent logs
curl "http://127.0.0.1:8083/api/logs/tail?n=20"

# Get current status
curl http://127.0.0.1:8083/api/status
```

#### Test Detection Pipeline
```bash
# Test window capture
python -m bsbot.tools.detect_cli --test-window --title "Brighter Shores"

# Test with screenshot
python -m bsbot.tools.detect_cli --test-screenshot assets/images/sample.png --word "Wendigo"
```

### 🔍 Common Issues & Solutions

#### 1. Window Not Found
**Symptoms:** "Window not found" error, blank preview

**Solutions:**
1. **Verify exact window title:**
   ```bash
   # List all window titles
   python -c "import win32gui; win32gui.EnumWindows(lambda hwnd, _: print(win32gui.GetWindowText(hwnd)), None)"
   ```

2. **Check window state:**
   - Ensure game is running and visible
   - Window should not be minimized
   - Try running game as administrator

3. **Update configuration:**
   ```yaml
   # config/profile.yml
   window_title: "Exact Game Window Title"
   ```

#### 2. OCR Detection Issues
**Symptoms:** No text detection, low confidence scores

**Solutions:**
1. **Verify Tesseract installation:**
   ```bash
   # Check if Tesseract is available
   tesseract --version
   ```

2. **Set Tesseract path:**
   ```bash
   # Via environment variable
   $env:TESSERACT_PATH = "C:\Program Files\Tesseract-OCR\tesseract.exe"

   # Via script parameter
   .\scripts\serve.ps1 -TesseractPath "C:\Program Files\Tesseract-OCR\tesseract.exe"
   ```

3. **Test OCR on known text:**
   ```bash
   python -c "import pytesseract, cv2; img = cv2.imread('test.png'); print(pytesseract.image_to_string(img))"
   ```

4. **Adjust OCR settings:**
   ```yaml
   # config/profile.yml
   confidence_threshold: 0.6  # Lower if too strict
   ```

#### 3. Template Detection Issues
**Symptoms:** Template matching fails, wrong detections

**Solutions:**
1. **Verify template exists and is valid:**
   ```bash
   # Check template file
   Test-Path "assets/templates/wendigo.png"
   ```

2. **Extract new template:**
   ```bash
   .\scripts\extract-template.ps1 -Screenshot screenshot.png -Template template.png
   ```

3. **Test template matching:**
   ```bash
   python -m bsbot.tools.detect_cli --test-window --template assets/templates/wendigo.png
   ```

4. **Adjust template settings:**
   ```yaml
   # config/profile.yml
   confidence_threshold: 0.75  # Template matching is usually more precise
   ```

#### 4. Live Click Issues
**Symptoms:** Clicks not registering, wrong click locations

**Solutions:**
1. **Enable dry-run mode first:**
   ```bash
   .\scripts\serve.ps1 -ClickMode "dry_run"
   ```

2. **Verify click coordinates:**
   - Check preview image for click markers
   - Verify ROI settings match game area

3. **Test input permissions:**
   - Ensure game window has focus
   - Try running bot as administrator

4. **Adjust click settings:**
   ```yaml
   # config/profile.yml
   input_delay_ms: 150  # Adjust timing
   ```

#### 5. Performance Issues
**Symptoms:** Slow detection, high CPU usage, lag

**Solutions:**
1. **Optimize ROI:**
   ```yaml
   # config/profile.yml
   roi_x: 0.2
   roi_y: 0.25
   roi_width: 0.6   # Smaller ROI = faster processing
   roi_height: 0.5
   ```

2. **Adjust scan interval:**
   ```yaml
   # config/profile.yml
   scan_interval_ms: 300  # Increase for less frequent scans
   ```

3. **Use template over OCR when possible:**
   ```yaml
   # config/profile.yml
   detection_method: "template"  # Faster than "ocr"
   ```

#### 6. Import/Dependency Errors
**Symptoms:** Module not found, version conflicts

**Solutions:**
1. **Reinstall environment:**
   ```bash
   # Remove old venv
   Remove-Item -Recurse -Force .venv

   # Reinstall
   .\scripts\setup.ps1
   ```

2. **Check Python version:**
   ```bash
   python --version  # Should be 3.11+
   ```

3. **Verify package installation:**
   ```bash
   python -c "import cv2, numpy, mss, pytesseract; print('All imports successful')"
   ```

### 🔧 Advanced Troubleshooting

#### Debug Mode
Enable detailed logging for deeper investigation:
```bash
# Run with debug logging
.\scripts\serve.ps1 -LogLevel DEBUG

# Check debug logs
Get-Content logs/app.log -Tail 50 -Wait
```

#### Network Diagnostics
Test API connectivity:
```bash
# Test all endpoints
curl http://127.0.0.1:8083/api/status
curl http://127.0.0.1:8083/api/diag
curl "http://127.0.0.1:8083/api/logs/tail?n=10"
```

#### Performance Profiling
Monitor system resources:
```bash
# Check memory usage
Get-Process python | Select-Object Name, CPU, Memory

# Monitor frame rate
# Check logs for "Runtime loop" messages
```

#### Screenshot Analysis
Capture and analyze problematic frames:
```bash
# Get live preview
curl -o debug.jpg http://127.0.0.1:8083/api/preview.jpg

# Test detection on specific screenshot
python -m bsbot.tools.detect_cli --test-screenshot debug.jpg --word "Target"
```

### 🚑 Emergency Procedures

#### Complete Reset
When nothing else works:
```bash
# Stop all processes
Get-Process python | Stop-Process -Force

# Clean environment
Remove-Item -Recurse -Force .venv, logs/*, __pycache__

# Reinstall from scratch
.\scripts\setup.ps1
.\scripts\serve.ps1
```

#### Safe Mode
Run with minimal features to isolate issues:
```bash
# Disable live clicks
.\scripts\serve.ps1 -ClickMode "dry_run"

# Use simple OCR only
# Set method to "ocr" in config
```

### 📞 Getting Help

#### Before Reporting Issues
1. **Gather information:**
   ```bash
   # System info
   systeminfo | findstr /C:"OS"

   # Python environment
   python --version
   python -c "import sys; print(sys.path)"

   # Dependencies
   python -c "import cv2, numpy, mss; print('Versions OK')"
   ```

2. **Capture error details:**
   ```bash
   # Full logs
   Get-Content logs/app.log -Tail 100 > error_log.txt

   # Screenshot of issue
   curl -o error_screenshot.jpg http://127.0.0.1:8083/api/preview.jpg
   ```

3. **Test with minimal setup:**
   - Use default configuration
   - Test with simple OCR detection
   - Verify window title is correct

#### Issue Report Template
When creating issues, include:
- **Description:** What you expected vs. what happened
- **Steps to reproduce:** Exact commands and configuration
- **Environment:** OS, Python version, dependency versions
- **Logs:** Relevant log excerpts
- **Screenshots:** Error screenshots or preview images
- **Configuration:** Your config files (sanitize sensitive data)

### 🎯 Prevention Tips

1. **Regular maintenance:**
   ```bash
   # Weekly cleanup
   Remove-Item logs/*.log -Exclude app.log
   ```

2. **Monitor health:**
   ```bash
   # Add to startup script
   .\scripts\check-docs.ps1
   ```

3. **Backup configurations:**
   ```bash
   # Backup configs before changes
   Copy-Item config/* config/backup/ -Recurse
   ```

4. **Test after updates:**
   ```bash
   # Quick test after changes
   python -m bsbot.tools.detect_cli --test-window
   ```

### 📚 Related Documentation

- **API Reference:** `docs/API.md` - Detailed endpoint documentation
- **Configuration Guide:** `docs/CONFIGURATION.md` - Config file schemas
- **Development Guide:** `docs/DEVELOPMENT.md` - Development setup and debugging
- **Architecture:** `docs/ARCHITECTURE.md` - System design and troubleshooting context

Repository Structure (key bits)
- `bsbot/` — main package
  - `ui/server.py` — Flask server for the UI
  - `runtime/service.py` — capture loop + skill orchestration
  - `skills/` — pluggable controllers (combat implemented, more to follow)
  - `vision/` — OCR and template detection primitives
  - `platform/` — Win32 helpers (windowing, capture, human-like input)
- `scripts/` — PowerShell helpers (`setup.ps1`, `serve.ps1`, `test-window.ps1`, `extract-template.ps1`)
- `assets/` — templates and screenshots (optional)
- `config/` — optional YAML configuration
- `logs/` — runtime logs
- `docs/` — comprehensive documentation
  - `ARCHITECTURE.md` — system design and components
  - `API.md` — endpoint documentation
  - `CONFIGURATION.md` — config file schemas
  - `DEVELOPMENT.md` — contributor guide
  - `OPERATIONS.md` — production/deployment
  - `DOC_MAINTENANCE.md` — documentation maintenance guide

## Documentation Maintenance

### For Contributors
- All code changes must include corresponding documentation updates
- Use the documentation templates in `docs/templates/` for consistency
- Run `scripts/check-docs.ps1` to validate documentation quality
- Documentation changes require review by the other agent

### For Users
- Documentation is kept current alongside code changes
- Check `docs/CHANGELOG.md` for recent updates
- Report documentation issues as GitHub issues

### Maintenance Schedule
- **Weekly**: Review recent commits for documentation gaps
- **Monthly**: Full documentation review and validation
- **Quarterly**: Comprehensive documentation audit

See `docs/DOC_MAINTENANCE.md` for detailed maintenance procedures.
