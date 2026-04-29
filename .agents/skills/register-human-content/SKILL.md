---
name: register-human-content
id: S-66
description: >
  Onboard a human-authored content page into quality and provenance systems; set auto_updatable: false, attach evidence, assign grade baseline
args: "{filepath}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-66: Register Human Content — Onboard Human-Authored Pages

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
   (run `/knowledge-bootstrap {family} {platform}`)
2. Grading infrastructure complete: `grade_writer.py` must exist at
   `scripts/pipeline/lib/grade_writer.py`
3. Evidence attachment infrastructure complete: `attach_evidence.py` must be available

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-66 --scope "*"
> ```


### Step 1: Identify the product scope

Parse `{filepath}` to extract `{family}` and `{platform}`:
```
content/{site}/en/{family}/{platform}/{page}.md
```

Confirm the knowledge model exists at `knowledge/{family}/{platform}/merged/model.yaml`.

### Step 2: Set provenance to human-authored

Open `{filepath}` and update (or add) the `provenance:` frontmatter block:

```yaml
provenance:
  content_origin: human-authored
  last_mechanism: human-edit
  auto_updatable: false
  reviewed: true
```

**Critical:** `auto_updatable: false` prevents translator sync and batch overwrites from
replacing this page. Do not change this unless the human explicitly requests it.

### Step 3: Attach evidence

```bash
python scripts/pipeline/commands/healing/attach_evidence.py --files {filepath}
```

This attaches an `evidence:` block with `model_sha`, `claims`, `apis`, and `formats`
derived from the page's content and the product knowledge model.

If `attach_evidence.py` returns errors about unknown API tokens: review and fix those
specific tokens in the page before proceeding. Unknown API tokens in human-authored pages
are content defects, not pipeline errors.

### Step 4: Assign quality grade baseline

Run S-25 (eval-page) to determine the current grade:
```bash
python -m scripts.pipeline.content_eval evaluate --files {filepath}
```

Then persist the grade:
```bash
python scripts/pipeline/lib/grade_writer.py --files {filepath}
```

Note the assigned grade. If grade is D or F, consider running S-26 (heal-page) before
finalizing. If grade is F due to critical FC/PC findings, escalate to human review per §8
before registering — do not protect a critically-wrong page from automated correction.

### Step 5: Run content-check gate

```bash
python scripts/pipeline/commands/content/audit.py --files {filepath}
```

A FAIL at this stage means the page has API accuracy problems. Fix them before proceeding.

### Step 6: Emit registration report

Write to `reports/human-content/{family}-{platform}-{slug}-{date}.json`:

```json
{
  "filepath": "{filepath}",
  "family": "{family}",
  "platform": "{platform}",
  "registered_at": "ISO timestamp",
  "grade": "A|B|C|D|F",
  "auto_updatable": false,
  "evidence_attached": true,
  "audit_result": "PASS|FAIL",
  "notes": ""
}
```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-66 --status completed
> ```

## Post-conditions

- `provenance.content_origin: human-authored` set in frontmatter
- `provenance.auto_updatable: false` set (page protected from automated overwrite)
- `evidence:` block attached with current knowledge model SHA
- Grade assigned and persisted in frontmatter
- Audit passes (no FAIL findings)
- Registration report written to `reports/human-content/`

## Failure handling

| Failure | Action |
|---------|--------|
| Knowledge model missing | Run `/knowledge-bootstrap {family} {platform}` first |
| Evidence attachment fails (unknown tokens) | Fix API references in the page; retry |
| Audit FAIL after evidence | Do not register; fix content defects first |
| Grade F with critical FC/PC finding | Escalate to human review per §8; do not protect |
| File is a locale variant (non-English path) | Do not register via this skill; locale files follow translator workflow |

## When NOT to use this skill

- Machine-generated pages (use the appropriate generation skill instead)
- Translator-produced locale files (use the translator workflow)
- Pages that should remain auto-updatable (omit this skill; leave default provenance)
