# Documentation Changelog

This file tracks significant documentation updates and improvements.

## [Unreleased]

### Added
- `docs/DOC_MAINTENANCE.md` - Comprehensive documentation maintenance guide
- `docs/templates/README_UPDATE.md` - Template for documentation updates
- `docs/API.md` - Complete API reference with endpoints, parameters, and examples
- `docs/CONFIGURATION.md` - Configuration schema documentation with examples
- `docs/DEVELOPMENT.md` - Developer onboarding guide with setup and workflows
- `docs/OPERATIONS.md` - Production deployment and operational procedures
- `scripts/check-docs.ps1` - Documentation health check script
- `.github/workflows/docs-check.yml` - CI workflow for documentation validation
- Documentation maintenance tasks in `docs/TASKS.md`

### Updated
- `README.md` - Comprehensive troubleshooting section and documentation maintenance info
- `docs/TASKS.md` - Added documentation maintenance tasks and rules
- `docs/CHANGELOG.md` - Documentation change tracking established
- `docs/DETECTION.md` - Documented compass alignment, hover gating, and minimap anchoring workflow
- `docs/ARCHITECTURE.md` - Added navigation components and tile-aware detection details
- `docs/OPERATIONS.md` - Production presets and health checks for compass/minimap telemetry
- `docs/STATUS.md` - Marked tile-aware roadmap (R1-5 → R1-11) complete with next-phase outlook
- `docs/CONFIGURATION.md` - Documented compass/minimap configuration blocks
- `docs/ARCHITECTURE.md` / `docs/CONFIGURATION.md` - Added interactable profiles and recorder workflow (with direct YAML save) documentation
- `docs/DETECTION.md` / `docs/CONFIGURATION.md` / `docs/OPERATIONS.md` / `docs/ARCHITECTURE.md` - Documented automatic template calibration workflow, new ROI override file, and calibration artefact locations
- `docs/DETECTION.md` - Recorded stability heuristics, fallback gating, and relaxed acceptance for first-time overrides; noted calibration telemetry now includes success streaks and stable flags
- `docs/CONFIGURATION.md` - Added pixel-based ROI configuration block that auto-scales with the live Win32 client size
- Template precedence clarified: runtime now applies monster/interface templates ahead of profile defaults, with override source surfaced in status
- Logging: per-run rollover added (keeps last five runs via RotatingFileHandler)

## Template for Future Entries

### [YYYY-MM-DD] - Version X.Y.Z

#### Added
- New documentation files or sections

#### Updated
- Modified existing documentation

#### Fixed
- Corrected documentation errors or outdated information

#### Removed
- Deprecated documentation sections

---

## Maintenance Notes

- All documentation changes should be recorded here
- Use semantic versioning for documentation releases
- Link to related code changes or issues where applicable
- Keep entries concise but descriptive

## Guidelines

1. **When to Add Entries**: Major documentation additions, significant updates, or corrections
2. **Entry Format**: Use present tense, start with action verb
3. **Grouping**: Group related changes under appropriate headings
4. **References**: Include PR numbers or issue references when applicable

Example:
```
### Added
- Comprehensive API documentation in `docs/API.md` (#123)
- Configuration schema documentation in `docs/CONFIGURATION.md` (#124)

### Updated
- Enhanced troubleshooting section in README.md
- Updated architecture diagrams in `docs/ARCHITECTURE.md`
```

---

*This changelog follows [Keep a Changelog](https://keepachangelog.com/) format*
