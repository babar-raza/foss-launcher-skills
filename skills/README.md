# Skills

This directory contains the **canonical source** for all registered skills in the aspose.org
content pipeline. Skills are the only sanctioned execution mechanism for content work in this
repo — ad hoc workflows are not permitted (AGENTS.md §6a (full detail: docs/governance/dar-table.md)).

> **Authoritative registry**: [AGENTS.md §12 (full table: docs/registries/skills.md)](../AGENTS.md) — machine-validated by CI.
> This README is a human navigation aid. When AGENTS.md §12 (full table: docs/registries/skills.md) and this file disagree, AGENTS.md wins.

---

## Invocation

Skills are invoked as slash commands from within the agent environment:

```
/skill-name {arguments}
```

Most content skills take `{family} {platform}` as arguments:

```
/batch-remediate 3d python
/knowledge-update slides net
/new-kb-howto cells python
```

Arguments for each skill are documented in its `**Arguments**` field at the top of the skill file.

Agent-specific paths:

| Agent | Skill path | Format |
|-------|-----------|--------|
| Claude Code | `.claude/commands/{name}.md` | flat `.md` |
| Codex CLI | `.agents/skills/{name}/SKILL.md` | per-folder |
| Kilo Code | `.kilocode/skills/{name}/SKILL.md` | per-folder |
| **Canonical source** | `skills/{name}.md` | flat `.md` ← you are here |

---

## Internal Sub-Routines

The following 8 skills are **auto-invoked** by other skills and are **never called directly** by
users or agents. They do not appear as user-callable commands in Claude Code.

| Slug | ID | Role |
|------|----|------|
| `knowledge-bootstrap` | S-54 | Pre-condition gate; detects and resolves stale knowledge before any content or validation command |
| `evidence-cite` | S-24 | Attaches knowledge citations; auto-invoked by generation skills before write |
| `path-guard` | S-01 | Enforces allowed write paths; auto-invoked on every write |
| `change-guard` | S-33 | Pre-write knowledge gate; auto-invoked before content writes |
| `no-downgrade-guard` | S-55 | Pre-write quality comparison; internal sub-routine called by generation skills |
| `rubric-align` | S-17 | Aligns content to quality rubric; sub-evaluator called by eval-page |
| `gap-plan` | S-44 | Wave-ordered remediation planning; sub-tool for the remediation pipeline |
| `project-phase-store` | S-10 | Tracks generation phase state; checkpoint infrastructure |

Source: `scripts/pipeline/commands/ops/sync_skills.py:INTERNAL_SKILLS`.

---

## Skill Catalog

81 registered skills grouped by functional category. For the machine-validated registry with
full descriptions, see [AGENTS.md §12 (full table: docs/registries/skills.md)](../AGENTS.md).

### Knowledge & Truth

Skills that maintain the knowledge model underpinning all content.

| ID | Slug | Purpose |
|----|------|---------|
| S-12 | `knowledge-diff` | Detect upstream repo changes |
| S-13 | `stale-detect` | Identify stale content pages |
| S-14 | `knowledge-update` | Refresh knowledge model from source |
| S-15 | `embed-knowledge` | Embed knowledge artifacts into dual vector stores |
| S-31 | `truth-index` | Generate knowledge index |
| S-34 | `repo-scout` | Extract truth from FOSS repository |
| S-35 | `truth-merge` | Promote scout + enriched claims into merged/ |
| S-37 | `knowledge-enrich` | LLM-enriched claims from scout api_surface (bounded-description mode) |
| S-38 | `truth-audit` | Member-level API verification (deep) |
| S-54 | `knowledge-bootstrap` | Pre-condition gate; detects and resolves stale knowledge *(internal)* |

### Generation

Skills that produce new content pages.

| ID | Slug | Purpose |
|----|------|---------|
| S-18 | `page-plan` | Plan page structure |
| S-19 | `page-draft` | Draft initial page content |
| S-22 | `faq-generate` | Generate FAQ section |
| S-47 | `site-plan` | Production-grade pre-generation site manifest (deterministic YAML output) |
| S-56 | `new-docs-page` | Generate documentation pages for docs.aspose.org |
| S-57 | `new-blog-post` | Generate blog posts for blog.aspose.org |
| S-58 | `new-kb-howto` | Generate KB how-to articles |
| S-59 | `new-kb-faq` | Generate or update FAQ page for a product platform |
| S-60 | `new-reference-page` | Generate API reference pages for reference.aspose.org |
| S-61 | `new-products-page` | Generate products.aspose.org landing pages |
| S-62 | `batch-reference` | Bulk reference page generation for all missing classes/enums; idempotent |
| S-69 | `new-kb-index` | Scaffold KB platform section landing page |
| S-70 | `new-docs-index` | Scaffold docs platform section landing page |
| S-71 | `new-reference-index` | Scaffold reference platform section landing page |

### Validation & Quality

Skills that verify content accuracy, quality, and structural compliance.

| ID | Slug | Purpose |
|----|------|---------|
| S-01 | `path-guard` | Enforce allowed write paths *(internal)* |
| S-17 | `rubric-align` | Align content to quality rubric *(internal)* |
| S-23 | `content-check` | Pre-write structural and quality check gate |
| S-25 | `eval-page` | Evaluate page grade |
| S-32 | `content-audit` | Semantic knowledge verification |
| S-33 | `change-guard` | Pre-write knowledge gate *(internal)* |
| S-36 | `cross-platform` | Family consistency check |
| S-43 | `gap-eval` | Content verification against clone cache — publishability verdict |
| S-51 | `content-eval` | Multi-dimensional content evaluation (16 evaluators, grading, batch mode) |
| S-55 | `no-downgrade-guard` | Pre-write quality comparison to prevent content regression *(internal)* |
| S-63 | `code-smoke` | Syntax and type-check Python code blocks in content files |
| S-65 | `link-validate` | Validate cross-subdomain internal links in content files |
| S-80 | `coverage-reconcile` | Trace every knowledge unit to a page disposition |
| S-81 | `knowledge-coverage-audit` | Per-claim disposition table |
| S-85 | `truth-audit-content` | Line-level content truth audit |

### Repair & Remediation

Skills that fix, heal, or improve existing content.

| ID | Slug | Purpose |
|----|------|---------|
| S-20 | `page-update` | Update page after knowledge change |
| S-21 | `page-enhance` | Enhance page to meet quality bar |
| S-26 | `heal-page` | Heal low-quality page |
| S-40 | `batch-remediate` | Full eval→fix→LLM→re-eval pipeline for all content pages of a product |
| S-41 | `batch-eval-fix` | Lightweight eval + deterministic auto-fixes only; no LLM pass |
| S-42 | `category-fix` | Run a specific fixer on files by category code |
| S-44 | `gap-plan` | Wave-ordered remediation planning from gap-eval findings *(internal)* |
| S-45 | `gap-report` | Cross-product gap synthesis report |
| S-46 | `gap-apply` | Execute wave-ordered fix specs from gap-plan output |
| S-72 | `evidence-repair` | Repair evidence frontmatter for validator-blocked pages |
| S-73 | `manual-edit` | Operator-directed targeted content edit: wording, frontmatter, code block, or section rewrite — single file, evidence-first, revert-on-failure |
| S-74 | `causal-backtrack` | Causal backtracking for root-cause-driven repair |
| S-78 | `evidence-enhance` | Improve section evidence coverage on passing pages |
| S-89 | `heal-batch` | Batch healing from eval report — eval→fix→re-eval pipeline driven by remediate.py |

### Operations & Orchestration

Skills that coordinate pipelines, manage translations, or support operators.

| ID | Slug | Purpose |
|----|------|---------|
| S-10 | `project-phase-store` | Track generation phase state for a product *(internal)* |
| S-24 | `evidence-cite` | Attach knowledge citations to content pages *(internal)* |
| S-48 | `family-sync` | Update family-level products page to reflect all launched platforms |
| S-49 | `launch-product` | 5-subdomain full documentation launch orchestrator (10 stages) |
| S-52 | `translate-page` | Translate a single English content page to target locales |
| S-53 | `translate-batch` | Batch translate all pages for a family/platform to target locales |
| S-64 | `getting-started` | Fresh-clone onboarding: install deps, configure env, bootstrap knowledge, verify |
| S-66 | `register-human-content` | Onboard a human-authored page into quality and provenance systems |
| S-67 | `diagnose-skill-failure` | Governed diagnostic procedure when a skill or pipeline script fails |
| S-68 | `update-registry` | Update product registry from knowledge model |
| S-75 | `locale-patch` | Propagate targeted text fixes to locale files |
| S-76 | `commit` | Full commit-prep workflow: inspect, categorize, plan commits, handle override tokens + content audit, stage precisely, verify tests, commit, clean up token lifecycle, print summary |
| S-77 | `session-start` | Mandatory session initialization gate |
| S-79 | `launch-rollback` | Revert one product's generated content files |
| S-82 | `delta-site-plan` | Incremental site planning after knowledge update |
| S-83 | `page-retire` | Retire obsolete content pages via Hugo draft flag |
| S-84 | `refresh-product` | Full post-launch product refresh orchestration (14-step chain from detect through commit) |
| S-86 | `refresh-product-page` | Re-generate a single products.aspose.org landing page through the full S-61 pipeline with no-downgrade-guard protection |
| S-87 | `system-heal` | Audit-driven content healing: 8-phase chain from gap-eval through commit |
| S-88 | `backlog` | Unified backlog management — view, update, add, triage, archive, remind, handoff |
| S-93 | `repo-patrol` | Discover new FOSS repos across 26 orgs, score confidence, produce patrol report |
| S-94 | `change-sweep` | Batch SHA comparison across all active products, classify impact HIGH/MEDIUM/LOW |
| S-95 | `discovery-triage` | Route patrol/sweep reports to backlog items (MVP: never invokes S-84 directly) |

---

## Dependency Chains

Major chains from AGENTS.md §6. Each step must be invoked in order; do not skip steps.

### Initial generation (new page)
```
S-10 (project-phase-store) → S-18 (page-plan) → S-19 (page-draft) → S-22 (faq-generate)
→ S-23 (content-check) → S-38 (truth-audit) → S-24 (evidence-cite) → S-01 (path-guard) → write
```

### Knowledge bootstrap
```
S-34 (repo-scout) → S-37 (knowledge-enrich) → S-35 (truth-merge) → S-31 (truth-index)
```

### Maintenance (upstream repo changed)
```
S-12 (knowledge-diff) → S-13 (stale-detect) → S-14 (knowledge-update)
→ S-20 (page-update) → S-23 (content-check) → S-24 (evidence-cite) → S-01 (path-guard) → write
```

### Enhancement (page below rubric quality)
```
S-17 (rubric-align) → S-21 (page-enhance) → S-23 (content-check) → S-01 (path-guard) → write
```

### Healing (grade D or below)
```
S-25 (eval-page) → S-26 (heal-page) → S-23 (content-check) → S-25 (eval-page) → S-01 (path-guard) → write
```

### Gap remediation (clone-cache verification + wave-ordered fixes)
```
S-43 (gap-eval) → S-44 (gap-plan) → S-46 (gap-apply) → S-23 (content-check) → S-01 (path-guard) → write
```
Wave 4 items from S-46 must be addressed via S-73 (manual-edit) — do not apply ad hoc fixes.

### Operator-directed targeted edit
```
S-73 (manual-edit) → embedded S-01 (path-guard) → embedded S-24 (evidence-cite) → write
```
Use when the operator specifies exactly what to change. For agent-decided fixes use S-26, S-21, or S-20.

### Batch reference page generation
```
S-62 (batch-reference) → S-38 (truth-audit, spot-check) → S-24 (evidence-cite) → S-01 (path-guard) → write
```

---

## Adding a New Skill

1. Create `skills/{slug}.md` following the structure of an existing skill (Purpose → Pre-conditions → Steps → Post-conditions → Error Handling)
2. Add an entry to AGENTS.md §12 (full table: docs/registries/skills.md) with the next available S-XX ID
3. Add a DAR entry in AGENTS.md §6a (full detail: docs/governance/dar-table.md) if the skill has upstream dependencies
4. Run `python scripts/ci/checks/check_skill_registry.py` — must exit 0
5. Run `python scripts/ci/checks/check_dar_coverage.py` — must exit 0
6. **Update the catalog table in this file** (skills/README.md) — add the new skill in the correct category
7. The sync mechanism (`sync_skills.py`) will flag if agent-specific mirrors diverge

---

## Related Documentation

- **[AGENTS.md](../AGENTS.md)** — canonical governance: skill-first mandate (§6, §6a, §6b), authoritative registry (§12)
- **[RUNBOOK.md](../RUNBOOK.md)** — operator quick-reference for common skill invocation patterns
- **[CODEX.md](../CODEX.md)** — Codex CLI agent instructions; `.agents/skills/` tree
- **[.claude/commands/README.md](../.claude/commands/README.md)** — Claude Code skill tree and invocation guide
