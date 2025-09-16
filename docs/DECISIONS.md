# Decisions Log

A lightweight log of key technical/product decisions. Append new entries at the top.

## 2025-09-16 — UI Modernization & Dark Theme
- Decision: Implement contemporary dark theme with CSS custom properties and professional gaming aesthetics.
- Reason: Better user experience, reduced eye strain, modern web standards, gaming industry conventions.
- Consequences: Enhanced visual hierarchy, improved accessibility, responsive design, easier maintenance via CSS variables.

## 2025-09-16 — OCR Deduplication Strategy
- Decision: Implement NMS (Non-Maximum Suppression) + size/aspect ratio filtering for OCR deduplication.
- Reason: OCR produces multiple overlapping detections; NMS provides mathematically sound deduplication; size filtering removes noise.
- Consequences: More stable detection counts, reduced false positives, better performance, configurable thresholds.

## 2025-09-16 — Package Architecture Migration
- Decision: Restructure from flat `src/` to layered `bsbot/` package with clear separation of concerns.
- Reason: Better maintainability, scalability, testing, and team collaboration; follows Python packaging best practices.
- Consequences: Import shims for backward compatibility, cleaner dependencies, easier feature isolation, professional codebase structure.

## 2025-09-16 — UI Template Separation
- Decision: Extract embedded HTML from Python code to separate Jinja2 templates.
- Reason: Better separation of concerns, easier UI development, template reusability, professional web development practices.
- Consequences: Cleaner Python code, easier UI iteration, template inheritance capabilities, improved maintainability.

## 2025-09-16 — Method Selection UI
- Decision: Add dropdown selector for Template/OCR/Auto detection modes with real-time switching.
- Reason: User control over detection strategy, better debugging, performance optimization, method comparison.
- Consequences: Dynamic runtime behavior, UI state management, method persistence, enhanced debugging capabilities.

## 2025-09-16 — R0-3 Cancellation
- Decision: Cancel R0-3 (Event Timeline) due to complexity and focus on core detection stability.
- Reason: Timeline added unnecessary complexity, potential threading issues, core detection needed stabilization first.
- Consequences: Simplified codebase, faster iteration, focus on proven detection improvements, ready for R1 combat features.

## 2025-09-16 — Detection Strategy and Controls
- Decision: Use edge-based template matching as primary for fixed UI words (e.g., Wendigo), OCR as fallback.
- Reason: Higher precision and meaningful confidence with fixed scale; OCR is noisy for HUD fonts.
- Consequences: Maintain template packs and a quick template-extractor; add small scale tolerance.
- Also: Global hotkeys (Ctrl+Alt+P pause/resume, Ctrl+Alt+O kill) are mandatory and must remain available.

## 2025-09-16 — Web UI and Port
- Decision: Serve the local control UI via Flask on 8083.
- Reason: Simple local hosting; fast iteration; embeddable status/preview/logs.
- Consequences: Keep endpoints stable; expand UI incrementally (method toggle, timeline, ROI editor).
