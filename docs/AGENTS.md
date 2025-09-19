# Agent Collaboration Guide (Scope: Repository Root)

This repository is designed for collaboration between multiple AI agents (e.g., Codex CLI and Groc5fast) and humans. Follow these conventions to coordinate safely and efficiently.

## Roles
- Codex (you): Product/Tech lead — owns roadmap, architecture, quality, and integration.
- Groc5fast: Fast implementer — focuses on well-scoped tasks defined in `docs/TASKS.md`, adhering to code style and tests.

## Coordination Protocol
- Source of truth for work items: `docs/TASKS.md` (single list with owners and states).
- Design decisions: append entries to `docs/DECISIONS.md` (date, context, decision, consequences).
- Status updates: `docs/STATUS.md` (short, current, human-readable).
- Architecture reference: `docs/ARCHITECTURE.md` (keep in sync with implementation).
- Session recap: append a row to the **Agent Activity Log** (see below) detailing scope, touched files, and hand-off notes before ending a run.

## Task Lifecycle
1. Create/Update a task in `docs/TASKS.md` with:
   - id, title, owner (`codex` or `groc5`), state (`todo|doing|review|done`)
   - acceptance criteria, affected files, test/validation steps
2. Implement minimal changes to satisfy acceptance criteria.
3. Validate locally (scripts in `scripts/`), attach any artifacts under `assets/`.
4. Update the task state and `docs/STATUS.md` succinctly.

## Coding Conventions
- Keep changes minimal and focused on the task.
- Prefer template detection; use OCR only as fallback.
- Build for Windows; PowerShell scripts live in `scripts/` and must run from anywhere.
- Log clearly to `logs/app.log`; avoid noisy stack traces in normal flow.
- Add tests only where adjacent patterns exist; otherwise keep lightweight runners in `bsbot/tools/detect_cli.py`.

## UI/Runtime Conventions
- Web UI on port 8083; avoid breaking existing endpoints.
- Expose detection status as structured JSON: `found`, `count`, `boxes`, `confidence`, `method`, `total_detections`.
- Hotkeys: Ctrl+Alt+P (pause/resume), Ctrl+Alt+O (kill) — do not change without updating docs and UI text.

## Templates & Assets
- Place templates in `assets/templates/` with descriptive names (e.g., `wendigo.png`).
- Place full screenshots in `assets/images/` for extraction/testing.
- Do not commit personal data.

## Communication Notes
- Write messages in tasks using explicit prefixes if helpful: `CODEX:` or `GROC5:`
- Keep comments short and action-oriented.

## Agent Activity Log

| date (UTC) | agent | focus | key changes | next steps |
|---|---|---|---|---|
| 2025-09-18 | codex | Detection roadmap integration | Added tile tracker scaffolding (`bsbot/tracking`), new config fields, roadmap docs (`docs/ARCHITECTURE.md`, `docs/DETECTION.md`), and task entries R1-5..R1-11. | 1) Implement compass auto-align + tile calibration. 2) Finish tile hover workflow + context ROI. 3) Automate minimap anchoring and expose tracker telemetry. |
| 2025-09-19 | codex | Tile-aware detection R1 completion | Implemented compass/minimap managers, tile calibration helpers & tests, hover-confirmed context clicks, expanded telemetry (`/api/status`), and refreshed docs/tasks. | 1) Wire live combat inputs (R1-2/R1-3). 2) Extend navigation beyond local tiles. |
| _fill on every session_ | | | | |

**How to use**
1. When you start, skim the previous entry to understand context.
2. When you finish, add a new row summarising what you did (link to tasks, PRs, or docs) and list explicit hand-off bullets.
3. Keep this table concise; detailed change history belongs in `docs/CHANGELOG.md` and Git commits.

## Safety & Scope
- Screen-based only (no memory reads).
- Be conservative with input automation; always keep a dry-run path during development.
- Preserve panic/stop controls and foreground checks before sending inputs (when implemented).

---

Last updated: now
