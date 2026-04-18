# Kilo Code Skills

This directory contains the **Kilo Code** version of the skill library.
Each skill is a subdirectory with a `SKILL.md` file inside.

> **Canonical source**: [skills/README.md](../../skills/README.md)
> **Authoritative registry**: [AGENTS.md §12](../../AGENTS.md)
> This tree is a full mirror of `skills/` — all 76 registered skills are present.
> When content diverges from canonical, investigate with `python scripts/pipeline/sync_skills.py --report`.

---

## Invocation

Skills are invoked using Kilo Code's built-in skill runner. Cross-skill references use
`/skill-name` syntax:

```
/skill-name {arguments}
```

Each skill's `SKILL.md` defines its arguments in the `**Arguments**` field.

Directory structure:
```
.kilocode/skills/
  batch-remediate/
    SKILL.md
  knowledge-update/
    SKILL.md
  ...
```

Governance rules for Kilo Code are in `.kilocode/rules-code/governance.md`.

---

## Skill List (72 skills — full canonical set)

All 72 registered skills are present in this tree. Internal sub-routines are included here
because Kilo Code invokes them directly when orchestrating skill chains.

| ID | Slug | Category | Internal? |
|----|------|----------|-----------|
| S-01 | `path-guard` | Validation | internal |
| S-10 | `project-phase-store` | Operations | internal |
| S-12 | `knowledge-diff` | Knowledge | |
| S-13 | `stale-detect` | Knowledge | |
| S-14 | `knowledge-update` | Knowledge | |
| S-15 | `embed-knowledge` | Knowledge | |
| S-17 | `rubric-align` | Validation | internal |
| S-18 | `page-plan` | Generation | |
| S-19 | `page-draft` | Generation | |
| S-20 | `page-update` | Repair | |
| S-21 | `page-enhance` | Repair | |
| S-22 | `faq-generate` | Generation | |
| S-23 | `content-check` | Validation | |
| S-24 | `evidence-cite` | Operations | internal |
| S-25 | `eval-page` | Validation | |
| S-26 | `heal-page` | Repair | |
| S-31 | `truth-index` | Knowledge | |
| S-32 | `content-audit` | Validation | |
| S-33 | `change-guard` | Validation | internal |
| S-34 | `repo-scout` | Knowledge | |
| S-35 | `truth-merge` | Knowledge | |
| S-36 | `cross-platform` | Validation | |
| S-37 | `knowledge-enrich` | Knowledge | |
| S-38 | `truth-audit` | Knowledge | |
| S-40 | `batch-remediate` | Repair | |
| S-41 | `batch-eval-fix` | Repair | |
| S-42 | `category-fix` | Repair | |
| S-43 | `gap-eval` | Validation | |
| S-44 | `gap-plan` | Repair | internal |
| S-45 | `gap-report` | Repair | |
| S-46 | `gap-apply` | Repair | |
| S-47 | `site-plan` | Generation | |
| S-48 | `family-sync` | Operations | |
| S-49 | `launch-product` | Operations | |
| S-51 | `content-eval` | Validation | |
| S-52 | `translate-page` | Operations | |
| S-53 | `translate-batch` | Operations | |
| S-54 | `knowledge-bootstrap` | Knowledge | internal |
| S-55 | `no-downgrade-guard` | Validation | internal |
| S-56 | `new-docs-page` | Generation | |
| S-57 | `new-blog-post` | Generation | |
| S-58 | `new-kb-howto` | Generation | |
| S-59 | `new-kb-faq` | Generation | |
| S-60 | `new-reference-page` | Generation | |
| S-61 | `new-products-page` | Generation | |
| S-62 | `batch-reference` | Generation | |
| S-63 | `code-smoke` | Validation | |
| S-64 | `getting-started` | Operations | |
| S-65 | `link-validate` | Validation | |
| S-66 | `register-human-content` | Operations | |
| S-67 | `diagnose-skill-failure` | Operations | |
| S-68 | `update-registry` | Operations | |
| S-69 | `new-kb-index` | Generation | |
| S-70 | `new-docs-index` | Generation | |
| S-71 | `new-reference-index` | Generation | |
| S-72 | `evidence-repair` | Repair | |
| S-73 | `manual-edit` | Repair | |
| S-74 | `causal-backtrack` | Repair | |
| S-75 | `locale-patch` | Operations | |
| S-76 | `commit` | Operations | |
| S-77 | `session-start` | Operations | |
| S-78 | `evidence-enhance` | Repair | |
| S-79 | `launch-rollback` | Operations | |
| S-80 | `coverage-reconcile` | Validation | |
| S-81 | `knowledge-coverage-audit` | Validation | |
| S-82 | `delta-site-plan` | Operations | |
| S-83 | `page-retire` | Operations | |
| S-84 | `refresh-product` | Operations | |
| S-85 | `truth-audit-content` | Validation | |
| S-86 | `refresh-product-page` | Operations | |
| S-87 | `system-heal` | Operations | |
| S-88 | `backlog` | Operations | |

---

## Sync & Validation

```bash
# Verify this tree matches canonical
.venv/Scripts/python scripts/pipeline/sync_skills.py --check

# View full divergence report
.venv/Scripts/python scripts/pipeline/sync_skills.py --report
```
