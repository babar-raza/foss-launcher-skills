---
name: llms-fidelity
id: S-LG-04
description: >
  Skill description pending
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-LG-04: llms-fidelity — Audit Content Fidelity

## Description

Samples source .md files and their corresponding .txt outputs, scoring fidelity
across title preservation, H2 count, code fence count, table row count,
and absence of shortcodes/evidence leakage. Gate: overall score >= 90%.

## Contract

**Backing script**: `scripts/generator/audit_fidelity.py`
**Input**: `content/` (source) + `llms-output/` (outputs)
**Output**: `reports/agent-consumption/fidelity-report.json` (local only)

## Steps

1. Quick fidelity check (10 pages per domain, random seed=42):
   ```bash
   .venv/Scripts/python scripts/generator/audit_fidelity.py \
     --content content \
     --output-dir llms-output \
     --report reports/agent-consumption/fidelity-report.json
   ```

2. Full corpus audit (all pages — use for TC-W8 regression gate):
   ```bash
   .venv/Scripts/python scripts/generator/audit_fidelity.py \
     --content content \
     --output-dir llms-output \
     --report reports/agent-consumption/fidelity-report.json \
     --full-corpus
   ```

3. Check score:
   ```bash
   .venv/Scripts/python -c "
   import json
   r = json.load(open('reports/agent-consumption/fidelity-report.json'))
   print(f'Overall score: {r[\"overall_score\"]}% [{r[\"gate\"]}]')
   for domain, d in r['domains'].items():
       if d['status'] != 'no_pages':
           print(f'  {domain}: {d[\"domain_score\"]}% ({d[\"failing_pages\"]} failing)')
   "
   ```

## Fidelity Dimensions (per page)

| Check | Description |
|-------|-------------|
| `title_preserved` | Frontmatter title appears in first 10 lines of output |
| `h2_count_ok` | Output H2 count >= source H2 count (headings not dropped) |
| `code_fence_count_ok` | Output code fences >= source code fences |
| `table_row_count_ok` | Output table rows >= source table rows |
| `no_shortcode` | No `{{` or `{%` in output (Hugo shortcodes not leaked) |
| `no_evidence_field` | No `claim_id:`, `model_sha:` in output (evidence not leaked) |

## Gate

Overall score >= 90%. Scores per page range 0-100%.
Pages scoring < 80% are counted as `failing_pages` per domain.

## Negative Control (manual verification)

To confirm the auditor correctly rejects false-complete outputs:
1. Take a source .md with a `## Limitations` section
2. Create a .txt without that section
3. Run auditor on that pair — score should be < 80% for that page

## Related Skills

- `/llms-generate` — regenerate to fix fidelity issues
- `/llms-coverage` — check presence (not quality)

## Metrics Obligation

This skill does not invoke LLM endpoints directly. No metrics obligation applies (METRICS-PLAN-001). It audits pre-generated output content against source pages only.
