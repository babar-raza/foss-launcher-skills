---
name: register-human-content
id: S-66
description: >
  Onboard a human-authored content page into quality and provenance systems;
  set auto_updatable: false, attach evidence, assign grade baseline.
args: "{content-file-path}"
---

# S-66: Register Human Content — Onboard Human-Authored Pages

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}` — path to the human-authored content file

## Purpose

Onboard a human-authored content page into the automated quality and provenance
systems. This skill: marks the page as human-authored, disables automated overwrite,
attaches evidence, assigns a quality grade baseline, and emits a registration report.

Use when a human contributor writes a page directly (not via a generation skill) and
that page needs to participate in quality enforcement, evidence validation, and grade
protection.

## Pre-conditions

1. Knowledge model must exist for the product:
   `knowledge/{family}/{platform}/merged/` with `model.yaml`, `claims.json`, `api_surface.json`
2. Run S-14 (knowledge-update) first if the knowledge is stale

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-66 --scope "{content-file-path}"
> ```

## Steps

### Step 1: Identify the product scope

Parse `{content-file-path}` to extract `{family}` and `{platform}`.

The path convention used by your repo is defined in `config.yaml` under `sites`.
For example, a path like `content/docs/{family}/{platform}/page.md` yields
`{family}` and `{platform}` from positions 3 and 4.

Confirm the knowledge model exists at `knowledge/{family}/{platform}/merged/model.yaml`.
If missing: **halt** — run S-14 (knowledge-update) first.

### Step 2: Set provenance to human-authored

Open `{content-file-path}` and update (or add) the `provenance:` frontmatter block:

```yaml
provenance:
  content_origin: human-authored
  last_mechanism: human-edit
  auto_updatable: false
  reviewed: true
```

**Critical:** `auto_updatable: false` prevents batch overwrites and translator sync
from replacing this page. Do not change this unless the human explicitly requests it.

### Step 3: Attach evidence

Match the page's content claims to `knowledge/{family}/{platform}/merged/claims.json`
and `api_surface.json`. Add or update the `evidence:` frontmatter block:

```yaml
evidence:
  model_sha: "{current model_sha from merged/model.yaml}"
  claims:
    - {claim_id}: "{claim text}"
  apis:
    - {ClassName.method_name}
```

If `scripts/attach_evidence.py` exists, use it:
```bash
python scripts/attach_evidence.py --files {content-file-path}
```

If the script finds unknown API tokens: **fix those tokens in the page first** before
proceeding. Unknown API tokens in human-authored pages are content defects.

If no script is available: run S-24 (evidence-cite) to attach citations manually.

### Step 4: Assign quality grade baseline

Run S-25 (eval-page) to determine the current grade. Note the assigned grade.

If grade is D or F: consider running S-26 (heal-page) before finalizing registration.
If grade is F due to critical accuracy findings: escalate to human review before
registering — do not protect a critically-wrong page from automated correction.

### Step 5: Run ground-check

Run S-23 (ground-check) on the file. A FAIL at this stage means the page has API
accuracy problems. Fix them before proceeding.

If `scripts/audit.py` exists:
```bash
python scripts/audit.py --files {content-file-path}
```

### Step 6: Emit registration report

Write to `reports/human-content/{family}-{platform}-{slug}-{YYYY-MM-DD}.json`:

```json
{
  "filepath": "{content-file-path}",
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

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-66 --status completed
> ```

## Post-conditions

- `provenance.content_origin: human-authored` set in frontmatter
- `provenance.auto_updatable: false` set (page protected from automated overwrite)
- `evidence:` block attached with current knowledge model SHA
- Grade assigned (D/F triggers heal recommendation)
- Ground-check (S-23) passes
- Registration report written to `reports/human-content/`

## Failure handling

| Failure | Action |
|---|---|
| Knowledge model missing | Run S-14 (knowledge-update) first |
| Evidence attachment finds unknown API tokens | Fix API references in the page; retry |
| Ground-check FAIL after evidence | Do not register; fix content defects first |
| Grade F with critical findings | Escalate to human review; do not protect |

## When NOT to use this skill

- Machine-generated pages (use the appropriate generation skill instead)
- Pages that should remain auto-updatable (omit this skill; leave default provenance)
- Locale/translation variants of a page (follow translation workflow instead)
