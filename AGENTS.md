# AGENTS.md — Content Generation & Maintenance Governance

> Last updated: 2026-03-18
> Authority: Human maintainer only — this file is in the forbidden write list
> Generated from: foss-launcher-skills AGENTS.template.md

## 1. Purpose

This repo is a standalone skill library that powers knowledge-grounded documentation
for Aspose FOSS products. Agents extract truth from FOSS repos via tree-sitter,
consolidate knowledge with provenance, and generate evidence-based content (docs,
blog posts, KB articles, API references) for a Hugo multisite. All content must be
traceable to the knowledge model — no hallucinated claims.

## 2. Read Order

Before any work, read in this order:

1. This file (`AGENTS.md`)
2. Agent instructions (`CLAUDE.md`, `CODEX.md`, or `.kilocode/rules-code/`) — if present
3. `config.yaml` — site paths, forbidden paths, golden corpus settings
4. `knowledge/{family}/{platform}/model.yaml` — for the target product
5. `knowledge/{family}/{platform}/claims.md` + `api_surface.md` — verify evidence

## 3. Mental Model Refresh

Before editing any content for family/platform X:

1. Read `knowledge/{family}/{platform}/model.yaml`
2. If `stale_since` is not null → **stop**. Run S-12 (knowledge-diff) + S-14 (knowledge-update) first
3. Read `claims.md` and `api_surface.md` for the product
4. Only then proceed to content tasks

## 4. Allowed Write Paths

Enforced by S-01 (path-guard). Mirrors `forbidden_paths` in `config.yaml`.

```
ALLOWED:
  content/docs.aspose.org/en/{family}/{platform}/
  content/blog.aspose.org/{family}/{platform}/
  content/kb.aspose.org/en/{family}/{platform}/
  content/products.aspose.org/en/{family}/
  content/reference.aspose.org/en/{family}/{platform}/
  knowledge/        (knowledge artifacts only)
  evidence/         (canonical evidence: PEF, mental model, verification, diffs, decisions)
  reports/          (audit and check reports)
  output/           (generated content, install tests)
  plans/            (page plans and healing workflows)

FORBIDDEN:
  themes/    layouts/    configs/
  AGENTS.md  CLAUDE.md   CODEX.md
  .claude/   .agents/    .kilocode/
  skills/    scripts/
```

## 5. Evidence Requirements

- Every content write must pass S-23 (ground-check) before commit
- Code blocks must come from `knowledge/{family}/{platform}/snippets/`
- Factual claims must trace to a `claim_id` in `claims.json`
- Claims with `confidence < 0.5` or `claim_source = "llm_fallback"` → human review
- Citation comments required: `<!-- evidence: claim_id={id} source={file} confidence={score} -->`

## 6. Skill Chains

**New page:**
S-10 → S-18 → S-19 → S-22 → S-23 → S-24 → S-01 → write

**Maintenance (repo changed):**
S-12 → S-13 → S-14 → S-20 → S-23 → S-24 → S-01 → write

**Enhancement (below rubric):**
S-17 → S-21 → S-23 → S-01 → write

**Healing (grade D or below):**
S-25 → S-26 → S-23 → S-25 → S-01 → write (or escalate)

**Product launch:**
S-38 orchestrates: S-34 → S-35 → S-31 → S-15 → S-37 → S-40 → S-41 → S-43 → [per-page chain] → S-36 → report

## 7. Hard Stops

Immediate halt, no override:

- S-01 path-guard returns `DENY`
- S-23 ground-check `FAIL` after 2 retries
- `model.yaml` `api_confidence = "low"`
- `claims.md` has `claim_source=llm_fallback` rate > 50%
- Page grade = F from S-25

## 8. Escalation (route to human)

- S-23 `FAIL` persists after remediation
- S-12 diff shows removed public class or changed method signature
- Stale report: > 30% of page claims orphaned
- S-26 heal loop fails after 2 attempts

## 9. Commit Requirements

Every commit touching content must include:

- Knowledge model SHA (`model.yaml` `repo_sha` value)
- Ground-check result: `PASS` (with report path)
- Skills invoked: `[S-xx, S-yy, ...]`

## 10. Agent Roles

Four roles, each with scoped skill access. Default is **writer** if undeclared.

| Role | Allowed Skills | Write Paths |
|------|---------------|-------------|
| **scout** | S-34, S-35, S-31, S-15, S-30, S-37, S-39, S-40, S-41, S-42, S-43 | `knowledge/`, `reports/`, `evidence/` |
| **writer** | S-10, S-18–S-22, S-24, new-* (gates: S-01, S-23) | `content/`, `plans/`, `output/`, `reports/` |
| **reviewer** | S-25, S-26, S-17, S-32, S-33, S-23, S-01, content-check, S-36 | `reports/`, `content/` |
| **orchestrator** | All skills | All allowed paths |

Role definitions: `config.yaml` → `governance.roles`

## 11. Autonomy Tiers

| Tier | Actions | Behaviour |
|------|---------|-----------|
| **AUTO** | Read, validate, extract, write reports, page plans | No approval needed |
| **WARN** | Write content pages, small knowledge updates | Proceed, flag `NEEDS_REVIEW` |
| **BLOCK** | Launch product, bulk updates, exceed limits | Pause for human approval |
| **HUMAN-ONLY** | Modify governance/skills/scripts, override stops | Agent must not attempt |

Session limits: 20 pages, 3 families, 3 consecutive fails → halt.

## 12. Audit Trail

- Session ID: `{YYYY-MM-DD}-{platform}-{role}`
- Log: `reports/agents/{session_id}.log` — one line per skill invocation
- Commits must include `Agent: {platform}/{role}` and `Session: {session_id}`

## 13. Key Paths

| Path | Purpose |
|------|---------|
| `skills/` | 36 canonical skill sources (YAML frontmatter + Markdown) |
| `scripts/` | Python engines: scout, merge, index, embed, corpus_scan, discover, materialize, mental_model, verify, differ, decide |
| `evidence/{family}/{platform}/` | Canonical evidence: PEF, mental model, verification reports, diffs, decisions |
| `configs/schemas/` | JSON schemas for evidence artifact validation |
| `tools/distribute.py` | Generates agent-specific skill dirs from canonical sources |
| `configs/families.yaml` | 21 product families × 13 platforms taxonomy |
| `configs/intake_config.yaml` | 24 GitHub orgs for product discovery |
| `config.yaml` | Site paths, forbidden paths, golden corpus settings |
| `knowledge/{family}/{platform}/` | Knowledge artifacts: model, claims, API surface, snippets |
| `reports/` | Audit outputs, launch reports |
| `reports/agents/` | Agent session audit logs |
| `.claude/commands/` | Claude Code skills (body only, frontmatter stripped) |
| `.agents/skills/` | Codex CLI skills (full frontmatter) |
| `.kilocode/skills/` | Kilo Code skills (full frontmatter) |

## 16. README Freshness

`README.md` is **not** in the forbidden write list — agents may update it under governance.

**Staleness detection**: `scripts/readme_sync.py --check` compares README content against
project state (skill count, script list, directory structure). It exits non-zero when stale.

**When to check**: After any of these events:
- A skill is added or removed from `skills/`
- A script is added or removed from `scripts/`
- A top-level directory is created or removed
- `configs/families.yaml` changes family or platform counts

**Autonomy tier**: **WARN** — agents may update README.md but must flag `NEEDS_REVIEW`
in the session log. Only the managed sections (skill catalog, project structure, script list,
skill count) should be auto-updated; prose sections require human editing.

**How to update**: Run `python scripts/readme_sync.py --check` to identify drift, then
update the relevant README sections to match the manifest from `python scripts/readme_sync.py`.

**Integration**: `tools/distribute.py --check-readme` prints a warning after distribution
if README is stale. Configured via `config.yaml` → `governance.readme_sync`.
