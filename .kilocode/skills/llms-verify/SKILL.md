---
name: llms-verify
id: S-LG-02
description: >
  Skill description pending
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-LG-02: llms-verify — Verify Live .txt Endpoints

## Description

Verifies live HTTP endpoints for all deployed llms-output .txt pages.
Samples ~50% of URLs per domain (plus pilot pages), checks HTTP 200 status,
content type, and structural content quality checks. Run after production deploy.

## Contract

**Backing script**: `scripts/generator/verify_live_txt_endpoints.py`
**Input**: `reports/llms-txt-verification/generated-txt-inventory.json`
**Output**: `reports/llms-txt-verification/live-verification-results.json` (local only)

## Prerequisite

Run `/llms-generate` first, then ensure a deploy has occurred (via aspose.org-workflows).
The inventory JSON must exist:
```bash
ls reports/llms-txt-verification/generated-txt-inventory.json
```

If missing, run `/llms-generate` + `.venv/Scripts/python scripts/generator/build_txt_inventory.py`

## Steps

1. Run basic HTTP verification (50% sample per domain):
   ```bash
   .venv/Scripts/python scripts/generator/verify_live_txt_endpoints.py
   ```

2. Run with deep content validation (10% sample, checks H2/code/tables):
   ```bash
   .venv/Scripts/python scripts/generator/verify_live_txt_endpoints.py --deep
   ```

3. Check results:
   ```bash
   cat reports/llms-txt-verification/live-verification-results.json
   ```

## Content Quality Checks (applied to fetched bodies)

- `no_angle_shortcodes` — no `{{` in output
- `no_percent_shortcodes` — no `{%` in output
- `has_title` — H1 heading present
- `no_evidence` — no `claim_id` or `model_sha` leakage
- `no_grading` — no `graded_content_hash` leakage
- `even_code_fences` — code fences come in pairs (no unclosed fences)
- `table_rows_valid` — tables have header + separator or none at all
- `h2_present_if_long` — pages >300 chars have at least one H2

## TC-07 Decision

Script reports `TC-07 decision: DEFERRED (all text/plain)` when no octet-stream content type detected.

## Related Skills

- `/llms-generate` — regenerate outputs before verifying
- `/llms-coverage` — audit local coverage (no HTTP required)

## Metrics Obligation

This skill does not invoke LLM endpoints directly. No metrics obligation applies (METRICS-PLAN-001). It performs HTTP verification of deployed endpoints only.
