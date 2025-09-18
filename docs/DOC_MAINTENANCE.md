# Documentation Maintenance Guide

## Overview
This guide outlines the processes and responsibilities for keeping documentation current and comprehensive.

## 1. Documentation Ownership Structure

### Primary Roles
- **Codex (Product/Tech Lead)**: Oversees documentation strategy, reviews major updates, maintains architecture docs
- **Groc5 (Fast Implementer)**: Updates operational docs, maintains API references, handles code documentation
- **Both Agents**: Responsible for documentation related to their tasks

### Documentation Areas & Owners

| Area | Primary Owner | Review Owner | Update Frequency |
|------|---------------|--------------|------------------|
| `README.md` | Shared | Codex | Pre-release |
| `docs/ARCHITECTURE.md` | Codex | Groc5 | Post-major-change |
| `docs/API.md` | Groc5 | Codex | Post-API-change |
| `docs/CONFIGURATION.md` | Shared | Codex | Post-config-change |
| `docs/DEVELOPMENT.md` | Codex | Groc5 | Monthly |
| `docs/OPERATIONS.md` | Groc5 | Codex | Quarterly |
| Code docstrings | Task Owner | Other Agent | With code changes |

## 2. Documentation Update Workflow

### Integration with Task System

#### For Every Task (R1-x, R2-x, etc.)
1. **Planning Phase**: Add documentation impact to acceptance criteria
2. **Implementation**: Update relevant docs alongside code changes
3. **Review**: Documentation updates reviewed before task completion

#### Example Task Format:
```
| R1-5 | Add fishing skill support | groc5 | doing | - Fishing detection working; - docs/API.md updated with new endpoints; - docs/CONFIGURATION.md includes fishing profiles; - README.md examples updated |
```

### Documentation PR Workflow
1. Code changes and documentation updates in same PR
2. Use PR description to highlight documentation changes
3. Require documentation review for PR approval

## 3. Regular Maintenance Activities

### Weekly Tasks
- [ ] Review recent commits for documentation gaps
- [ ] Update task status documentation
- [ ] Check for broken links in documentation

### Monthly Tasks
- [ ] Full documentation review for accuracy
- [ ] Update development environment docs
- [ ] Review and update troubleshooting section
- [ ] Validate all code examples

### Quarterly Tasks
- [ ] Comprehensive documentation audit
- [ ] Update roadmap and architecture diagrams
- [ ] Review operational procedures
- [ ] Update contribution guidelines

## 4. Documentation Standards

### File Organization
```
docs/
├── ARCHITECTURE.md      # System design and components
├── API.md               # Endpoint documentation
├── CONFIGURATION.md     # Config file schemas
├── DEVELOPMENT.md       # Contributor guide
├── OPERATIONS.md        # Production/deployment
├── MAINTENANCE.md       # This file
└── README.md           # Updated with maintenance section
```

### Content Standards
- **Accuracy**: All examples must be tested and working
- **Completeness**: Cover common use cases and error scenarios
- **Consistency**: Use consistent terminology and formatting
- **Timeliness**: Update within 1 week of code changes

### Code Documentation Standards
- All public functions need docstrings
- Complex algorithms need inline comments
- Configuration files need schema comments
- API endpoints need parameter documentation

## 5. Automation & Tools

### Git Hooks (Recommended)
- Pre-commit hook to check for documentation changes when code is modified
- Post-commit hook to validate documentation links

### CI/CD Integration
```yaml
# Add to CI pipeline
- name: Validate Documentation
  run: |
    # Check for broken links
    # Validate code examples
    # Check documentation completeness
```

### Documentation Linting
- Use markdown linters for consistent formatting
- Custom scripts to validate API documentation against actual endpoints
- Link checkers for internal documentation references

## 6. Quality Assurance

### Documentation Review Checklist
- [ ] All code examples are functional
- [ ] Configuration examples match actual schemas
- [ ] API documentation matches implementation
- [ ] Troubleshooting covers recent issues
- [ ] Links are valid and current
- [ ] Screenshots/images are up to date

### Peer Review Process
1. Documentation changes require review by other agent
2. Use GitHub PR reviews for documentation updates
3. Maintain documentation changelog for major updates

## 7. Metrics & Monitoring

### Documentation Health Metrics
- **Coverage**: Percentage of code with documentation
- **Freshness**: Age of documentation vs last code changes
- **Accuracy**: Rate of documentation issues found by users
- **Completeness**: Documentation completeness score

### Monitoring Tools
- Track documentation update frequency
- Monitor for outdated examples
- Alert when API changes lack documentation updates

## 8. Emergency Procedures

### When Documentation is Outdated
1. **Immediate**: Add "⚠️ OUTDATED" warning to affected sections
2. **Short-term**: Create task to update documentation
3. **Long-term**: Review why documentation became outdated

### Missing Documentation
1. **Critical gaps**: Block release until documented
2. **Minor gaps**: Create follow-up task with deadline
3. **Nice-to-have**: Add to backlog for future sprints

## 9. Training & Onboarding

### New Contributor Documentation
- Require documentation updates as part of contribution process
- Provide documentation templates for common changes
- Include documentation review in code review process

### Documentation Champions
- Rotate documentation maintenance responsibilities
- Provide training on documentation tools and standards
- Recognize contributions to documentation quality

---

## Implementation Checklist

- [ ] Create documentation maintenance tasks in TASKS.md
- [ ] Update AGENTS.md with documentation responsibilities
- [ ] Add documentation review to PR template
- [ ] Set up basic documentation linting
- [ ] Create documentation update templates
- [ ] Establish quarterly documentation audit schedule

---

*Last Updated: $(date)*
*Maintained by: Codex & Groc5*
