# Claude Code Skills

This directory contains the **Claude Code** version of the skill library.
Skills here are invoked as slash commands within Claude Code sessions.

> **Canonical source**: [skills/README.md](../../skills/README.md)
> **Authoritative registry**: [AGENTS.md §12](../../AGENTS.md)
> This tree is a mirror of `skills/` with Claude Code-specific adaptations. When content diverges,
> investigate with `sync_skills.py --report`, then fix it with
> `python scripts/pipeline/commands/ops/sync_providers.py` (the report-only tool never writes
> anything itself).

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

This tree (100 files) differs from the canonical `skills/` (107 files) in two ways:

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
| `translate.md` | RETIRED TOMBSTONE: permanently retired; instructs callers to use hugo-translator with explicit --site profile. |
| `seo-review.md` | Interactive human review gate for SEO recommendations. Claude Code-only utility; not yet a first-class registered skill. |

Source: `scripts/pipeline/commands/ops/sync_skills.py:KNOWN_EXCEPTIONS` and `INTERNAL_SKILLS`.

---

## Skill List (112 registered skills available in this tree)

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
| S-HT-01 | `ht-translate` | Operations |
| S-HT-02 | `ht-translate-batch` | Operations |
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
| S-68 | `update-registry` | Operations |
| S-69 | `new-kb-index` | Generation |
| S-70 | `new-docs-index` | Generation |
| S-71 | `new-reference-index` | Generation |
| S-72 | `evidence-repair` | Repair |
| S-73 | `manual-edit` | Repair |
| S-74 | `causal-backtrack` | Repair |
| S-75 | `locale-patch` | Operations |
| S-76 | `commit` | Operations |
| S-77 | `session-start` | Operations |
| S-78 | `evidence-enhance` | Repair |
| S-79 | `launch-rollback` | Operations |
| S-80 | `coverage-reconcile` | Validation |
| S-81 | `knowledge-coverage-audit` | Validation |
| S-82 | `delta-site-plan` | Operations |
| S-83 | `page-retire` | Operations |
| S-84 | `refresh-product` | Operations |
| S-85 | `truth-audit-content` | Validation |
| S-86 | `refresh-product-page` | Operations |
| S-87 | `system-heal` | Operations |
| S-88 | `backlog` | Operations |
| S-89 | `heal-batch` | Repair |
| S-93 | `repo-patrol` | Operations |
| S-94 | `change-sweep` | Operations |
| S-95 | `discovery-triage` | Operations |
| S-96 | `section-enhance` | Validation |
| S-97 | `cleanroom-regen` | Operations |
| S-98 | `content-enrich` | Operations |
| S-99 | `pipeline-harden` | Operations |
| S-100 | `blog-migrate` | Operations |
| S-101 | `new-blog-index` | Generation |
| S-102 | `grade-remediate` | Repair |
| S-103 | `post-sprint-loop` | Operations |
| S-115 | `workflow-harden` | Operations |

---

## Sync & Validation

```bash
# Verify this tree matches canonical
.venv/Scripts/python scripts/pipeline/commands/ops/sync_skills.py --check

# View full divergence report
.venv/Scripts/python scripts/pipeline/commands/ops/sync_skills.py --report

# Actually fix drift — sync_skills.py above only detects it, never writes anything.
# This is the command that propagates skills/*.md into this tree (and .agents/, .kilocode/):
.venv/Scripts/python scripts/pipeline/commands/ops/sync_providers.py
```

CI runs `sync_skills.py --check` on every push/PR that modifies `skills/**`, `.agents/skills/**`,
`.claude/commands/**`, or `.kilocode/skills/**` (`.github/workflows/skill-governance.yml`).
A pre-commit gate additionally blocks any local commit that touches a skill whose canonical and
mirror copies have diverged — run `sync_providers.py` (not just `--check`) before committing.

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
