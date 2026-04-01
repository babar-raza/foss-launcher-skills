# Claude Code Skills

This directory contains the **Claude Code** version of the skill library.
Skills here are invoked as slash commands within Claude Code sessions.

> **Canonical source**: [skills/README.md](../../skills/README.md)
> **Authoritative registry**: [AGENTS.md §12](../../AGENTS.md)
> This tree is a mirror of `skills/` with Claude Code-specific adaptations. When content diverges,
> investigate using `python scripts/pipeline/sync_skills.py --report`.

---

## Invocation

```
/skill-name {arguments}
```

Examples:
```
/batch-remediate 3d python
/knowledge-update slides net
/new-kb-howto cells python
/getting-started
```

Arguments for each skill are documented in the `**Arguments**` line at the top of each file.

---

## This Tree vs Canonical

This tree (43 files) differs from the canonical `skills/` (51 files) in two ways:

### 1. Internal sub-routines are omitted (8 skills)

These skills are auto-invoked by other skills and are never called directly. They are present in
`skills/` and in `.agents/skills/` but are intentionally absent here because Claude Code exposes
them as automatic behavior, not user-visible commands.

| Slug | ID | Why omitted |
|------|----|-------------|
| `knowledge-bootstrap` | S-54 | Auto-invoked as pre-condition gate before content/validation commands |
| `evidence-cite` | S-24 | Auto-invoked by generation skills before write |
| `path-guard` | S-01 | Auto-enforced on every write |
| `change-guard` | S-33 | Auto-invoked before content writes |
| `no-downgrade-guard` | S-55 | Internal quality comparison sub-routine |
| `rubric-align` | S-17 | Sub-evaluator called by eval-page |
| `gap-plan` | S-44 | Planning sub-tool for remediation pipeline |
| `project-phase-store` | S-10 | Checkpoint infrastructure |

### 2. Claude-only extras (2 files)

These files exist only in this tree. They are not registered in AGENTS.md §12 and have no
counterpart in `skills/`, `.agents/skills/`, or `.kilocode/skills/`.

| File | Role |
|------|------|
| `translate.md` | Dispatcher: routes to `/translate-page` (S-52) or `/translate-batch` (S-53) based on argument type. Convenience wrapper only — adds no new capability. |
| `seo-review.md` | Interactive human review gate for SEO recommendations. Claude Code-only utility; not yet a first-class registered skill. |

Source: `scripts/pipeline/sync_skills.py:KNOWN_EXCEPTIONS` and `INTERNAL_SKILLS`.

---

## Skill List (43 registered skills available in this tree)

| ID | Slug | Category |
|----|------|----------|
| S-12 | `knowledge-diff` | Knowledge |
| S-13 | `stale-detect` | Knowledge |
| S-14 | `knowledge-update` | Knowledge |
| S-15 | `embed-knowledge` | Knowledge |
| S-18 | `page-plan` | Generation |
| S-19 | `page-draft` | Generation |
| S-20 | `page-update` | Repair |
| S-21 | `page-enhance` | Repair |
| S-22 | `faq-generate` | Generation |
| S-23 | `content-check` | Validation |
| S-25 | `eval-page` | Validation |
| S-26 | `heal-page` | Repair |
| S-31 | `truth-index` | Knowledge |
| S-32 | `content-audit` | Validation |
| S-34 | `repo-scout` | Knowledge |
| S-35 | `truth-merge` | Knowledge |
| S-36 | `cross-platform` | Validation |
| S-37 | `knowledge-enrich` | Knowledge |
| S-38 | `truth-audit` | Knowledge |
| S-40 | `batch-remediate` | Repair |
| S-41 | `batch-eval-fix` | Repair |
| S-42 | `category-fix` | Repair |
| S-43 | `gap-eval` | Validation |
| S-45 | `gap-report` | Repair |
| S-46 | `gap-apply` | Repair |
| S-47 | `site-plan` | Generation |
| S-48 | `family-sync` | Operations |
| S-49 | `launch-product` | Operations |
| S-51 | `content-eval` | Validation |
| S-52 | `translate-page` | Operations |
| S-53 | `translate-batch` | Operations |
| S-56 | `new-docs-page` | Generation |
| S-57 | `new-blog-post` | Generation |
| S-58 | `new-kb-howto` | Generation |
| S-59 | `new-kb-faq` | Generation |
| S-60 | `new-reference-page` | Generation |
| S-61 | `new-products-page` | Generation |
| S-62 | `batch-reference` | Generation |
| S-63 | `code-smoke` | Validation |
| S-64 | `getting-started` | Operations |
| S-65 | `link-validate` | Validation |
| S-66 | `register-human-content` | Operations |
| S-67 | `diagnose-skill-failure` | Operations |

---

## Sync & Validation

```bash
# Verify this tree matches canonical
python scripts/pipeline/sync_skills.py --check

# View full divergence report
python scripts/pipeline/sync_skills.py --report
```

CI runs this check on every PR that modifies content. Drift from canonical is reported but
currently advisory (`continue-on-error: true`).
