---
name: register-human-content
id: S-71
description: >
  Onboard a human-authored content page into the automated quality and provenance
  systems. Marks the page as human-authored, disables automated overwrite, attaches
  evidence, assigns a quality grade baseline, and emits a registration report.
args: "{filepath}"
---

# S-71: Register Human Content — Onboard Human-Authored Pages

**Arguments**: $ARGUMENTS
Expected format: `{filepath}` — path to the human-authored content file (relative to repo root)

## Purpose

Onboard a human-authored content page into the automated quality and provenance systems.
This skill: marks the page as human-authored, disables automated overwrite, attaches
evidence, assigns a quality grade baseline, and emits a registration report.

Use when a human contributor writes a page directly (not via a generation skill) and that
page needs to participate in quality enforcement, evidence validation, and grade protection.

## Pre-conditions

1. Knowledge bootstrap confirmed for the product in the file's `{family}/{platform}` path
2. File exists at `{filepath}` and is a valid Markdown content file
3. File is an English source file (not a locale variant)

## Steps

1. **Parse arguments**: Extract `{filepath}`. Derive `{family}` and `{platform}` from the path.

2. **Knowledge bootstrap check**:
   Run `/knowledge-bootstrap {family} {platform}` and confirm `READY` or `BOOTSTRAPPED`.
   If `STOP:partial` → halt.

3. **Read the file**: Load full content including frontmatter.

4. **Set provenance block** in frontmatter:
   ```yaml
   provenance:
     content_origin: human
     last_mechanism: human
     auto_updatable: false
     registered_at: "{ISO date}"
   ```
   `auto_updatable: false` prevents automated skills (S-20, S-26, etc.) from overwriting
   this page without explicit operator override.

5. **Attach evidence**:
   ```bash
   python scripts/pipeline/attach_evidence.py --files {filepath} --force
   ```

6. **Assign baseline grade**:
   ```bash
   python -m scripts.pipeline.content_eval evaluate --files {filepath} --format json
   ```
   Record the baseline grade. Human pages are exempt from automated heal escalation if grade >= B.

7. **Run audit**:
   ```bash
   python scripts/pipeline/audit.py --files {filepath}
   ```
   Human-authored pages with audit FAILs should be reviewed — report but do not block registration.

8. **Emit registration report** to `reports/human-content/registrations.md`:
   ```markdown
   | {filepath} | {date} | {grade} | {audit status} |
   ```

9. **Confirm registration**:
   ```
   REGISTERED: {filepath}
   Author:     human
   Grade:      {grade}
   Audit:      PASS | WARN | FAIL (see report)
   Auto-updatable: false
   ```

## Post-conditions

- `provenance.content_origin: human` in frontmatter
- `provenance.auto_updatable: false` in frontmatter
- Evidence block attached
- Baseline grade assigned
- Registration recorded in `reports/human-content/registrations.md`

## Hard rules

- Never set `auto_updatable: true` for human-authored pages
- Never invoke this skill on skill-generated pages (use evidence-repair S-77 instead)
- Grade FAILs do not block registration but must be documented
