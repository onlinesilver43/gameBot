# Documentation Update Template

## When to Use This Template
Use this template when making changes that affect user-facing documentation.

## Template Checklist

### 1. Code Changes Made
- [ ] Feature implementation completed
- [ ] API endpoints added/modified
- [ ] Configuration schema changes
- [ ] New dependencies added

### 2. Documentation Updates Required

#### README.md Updates
- [ ] Installation instructions updated
- [ ] Usage examples added/modified
- [ ] Configuration examples updated
- [ ] Troubleshooting section updated
- [ ] New command-line options documented

#### API Documentation (docs/API.md)
- [ ] New endpoints documented
- [ ] Request/response formats updated
- [ ] Parameter validation rules documented
- [ ] Error response codes documented

#### Configuration Documentation (docs/CONFIGURATION.md)
- [ ] New configuration options documented
- [ ] Schema changes explained
- [ ] Example configurations updated
- [ ] Environment variable overrides documented

#### Architecture Documentation (docs/ARCHITECTURE.md)
- [ ] System components updated
- [ ] Data flows modified
- [ ] State machines changed
- [ ] Performance characteristics updated

### 3. Testing & Validation
- [ ] All documentation examples tested
- [ ] Links validated
- [ ] Code snippets syntactically correct
- [ ] Screenshots updated (if applicable)

### 4. Review & Approval
- [ ] Peer review completed
- [ ] Documentation changes approved
- [ ] Changelog updated (if applicable)

## Quick Update Commands

```bash
# Validate all documentation links
find docs/ -name "*.md" -exec grep -l "http" {} \; | xargs -I {} markdown-link-check {}

# Check for common documentation issues
find docs/ -name "*.md" -exec grep -n "TODO\|FIXME\|XXX" {} \;

# Generate documentation table of contents
find docs/ -name "*.md" | sort | sed 's|docs/|- [$(basename {} .md)]({})\n|g'
```

## Change Documentation

| Date | Change Type | Files Affected | Reviewer |
|------|-------------|----------------|----------|
| YYYY-MM-DD | [ADD/MODIFY/REMOVE] | [list files] | [reviewer] |

## Notes
[Any additional context or special considerations for this documentation update]
