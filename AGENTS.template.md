# AGENTS.md — Content Generation & Maintenance Governance

> Last updated: {DATE}
> Authority: Human maintainer only (see Section 4 — this file is in the forbidden write list)
> Generated from: foss-launcher-skills AGENTS.template.md

## 1. Purpose

Agents operating on this repo generate and maintain documentation for FOSS products.
All content must be grounded in evidence from the knowledge model. This file is the
authoritative source of operating rules for all agents.

## 2. Session Start Gate

**Mandatory first action every session**: invoke S-77 (session-start) before any task.

S-77 reads this file, surfaces backlog reminders, initializes the session ledger (if configured),
and states the skill-first mandate. Do not begin work until S-77 has completed.

## 3. Read Order (always read in this order before doing any work)

1. This file (AGENTS.md)
2. Agent instructions file (`CLAUDE.md`, `CODEX.md`, or `.kilocode/rules-code/`) — if present
3. `knowledge/{family}/{platform}/model.yaml` — for the target product
4. `knowledge/{family}/{platform}/claims.md` — verify claims are current
5. `knowledge/{family}/{platform}/api_surface.md` — for API grounding

## 4. Mental Model Refresh Protocol

Before editing any content page for family/platform X:

1. Read `knowledge/{family}/{platform}/model.yaml`
2. If `stale_since` is not null → the knowledge model is outdated; do not edit content until
   a knowledge-diff (S-12) and knowledge-update (S-14) have been run
3. Read `claims.md` and `api_surface.md` for the product
4. Only then proceed to content tasks

## 5. Allowed Write Paths (enforced by S-01 path-guard)

> **Customize these paths for your project.** The defaults below match the aspose.org
> Hugo multisite layout. Update to reflect your content directory structure.

```
ALLOWED:
  content/docs.aspose.org/en/{family}/{platform}/
  content/blog.aspose.org/{family}/{platform}/
  content/kb.aspose.org/en/{family}/{platform}/
  content/products.aspose.org/en/{family}/
  content/reference.aspose.org/en/{family}/{platform}/
  knowledge/   (evidence artifacts and model only)
  reports/     (audit and check reports)

FORBIDDEN (no agent may write here without explicit human override):
  themes/
  layouts/
  configs/
  CLAUDE.md
  CODEX.md
  AGENTS.md    (this file — only humans may update it)
  .claude/     (Claude Code config)
  .agents/     (Codex config)
  .kilocode/   (Kilo Code config)
  skills/      (canonical skill source — only humans may update)
```

## 6. Evidence Requirements (non-negotiable)

- Every content page write must pass S-23 (ground-check) before committing
- Every code block in `content/` must come from a snippet in `knowledge/{family}/{platform}/snippets/`
- Every factual claim must be traceable to a `claim_id` in `knowledge/{family}/{platform}/claims.json`
- Claims with `confidence < 0.5` or `claim_source = "llm_fallback"` require human review before use
- Citation comments `<!-- evidence: claim_id={id} source={file} confidence={score} -->` must be
  present in every content page (added by S-24 evidence-cite)

## 7. Skill Chains by Task

### Initial generation (new page)

```
S-10 (project-phase-store) → S-18 (page-plan) → S-19 (page-draft) → S-22 (faq-generate)
→ S-23 (ground-check) → S-24 (evidence-cite) → S-01 (path-guard) → write
```

### Maintenance (repo changed)

```
S-12 (knowledge-diff) → S-13 (stale-detect) → S-14 (knowledge-update) → S-20 (page-update)
→ S-23 → S-24 → S-01 → write
```

### Enhancement (below rubric quality)

```
S-17 (rubric-align) → S-21 (page-enhance) → S-23 → S-01 → write
```

### Healing (grade D or below)

```
S-25 (eval-page) → S-26 (heal-page) → S-23 → S-25 → S-01 → write (or escalate)
```

If S-26 fails to improve grade after 2 passes: escalate to **S-73 (manual-edit)**.
S-73 is the only sanctioned path for operator-directed content changes. Never edit
content files directly outside S-73 or the skill chain above.

### Operator-directed edit (typo, wording, targeted fix)

```
S-73 (manual-edit) {file} --scope {scope} --intent "{what and why}"
```

S-73 validates the change, runs ground-check, refreshes evidence, and records an audit trail.
Never edit content files directly — always invoke S-73.

### Session recording

```
S-76 (commit) at session end — stages session-touched files, runs tests, commits with evidence metadata
```

### Backlog management

```
S-88 (backlog) — view current state, add items, update, triage, handoff
/backlog           — session-start briefing (reminders + handoff + active items)
/backlog handoff   — write session summary at session end
```

### New FOSS product launch (all pages from scratch)

```
S-38 (launch-product) orchestrates:
  Phase 1 (knowledge): S-34 → S-35 → S-31 → S-15* → S-37   (* if vector store configured)
  Confidence gate: api_confidence must not be "low"
  Phase 2 (pages):     [S-10 → S-18 → S-19 → S-23 → S-24 → S-01 → write] × each page type
  Phase 3 (consistency): S-36*                                              (* if sibling platforms exist)
  Phase 4 (report):    writes reports/launch/{family}-{platform}-{timestamp}.md
```

## 8. Hard Stop Conditions

The following always cause immediate halt (no agent override):

- S-01 path-guard returns `DENY`
- S-23 ground-check returns `FAIL` after 2 retries
- `knowledge/model.yaml.api_confidence = "low"`
- `knowledge/claims.md` has `claim_source=llm_fallback` rate > 50%
- Page grade = F (critical finding) from S-25

## 9. Escalation Conditions (route to human review)

- S-23 `FAIL` persists after remediation
- S-12 diff reveals removed public class or changed method signature
- `stale_report` shows > 30% of page claims are orphaned
- Heal loop (S-26) fails to improve grade after 2 attempts

## 10. Maintenance Workflow

**Trigger**: `knowledge/model.yaml.stale_since` is not null (repo has changed)

1. S-12 (diff) — identify which files changed
2. S-13 (stale-detect) — which content pages are affected
3. For each affected page: S-14 → S-20 → S-25
4. S-15 (embed-knowledge) — sync vector store if used
5. Commit: `knowledge/` changes + `content/` changes together

## 11. Evidence Proof in Commits

Every commit touching `content/` MUST include in the commit message:

- Knowledge model SHA: `knowledge/{family}/{platform}/model.yaml` `repo_sha` value
- Ground-check result: `PASS` (with report path)
- Skills invoked: `[S-xx, S-yy, ...]`

Citation comments in pages are the inline persistent evidence.

## 12. Prohibited Actions

- Write API method names not present in `knowledge/{family}/{platform}/api_surface.md`
- Write format claims not present in `knowledge/{family}/{platform}/formats.md`
- Generate code blocks using LLM — all code must come from `snippets/`
- Skip S-23 ground-check for any reason
- Write to forbidden paths listed in Section 4

## 13. Agent Roles

Each agent session operates under one of four roles. The role determines which
skills the agent may invoke and where it may write. Default role is **writer**.

| Role | Allowed Skills | Write Paths | Notes |
|------|---------------|-------------|-------|
| **scout** | S-34, S-35, S-31, S-15, S-30, S-37, S-39 | `knowledge/`, `reports/` | Extracts and consolidates knowledge. Never writes content pages. |
| **writer** | S-10, S-18, S-19, S-20, S-21, S-22, S-24, new-* | `content/`, `plans/`, `output/`, `reports/` | Generates and updates content. Gates S-01 + S-23 are mandatory. |
| **reviewer** | S-25, S-26, S-17, S-32, S-33, S-23, S-01, content-check, S-36 | `reports/`, `content/` | Evaluates, audits, and heals content. Content writes only via heal chain. |
| **orchestrator** | All skills | All allowed paths | Runs full launches (S-38). Subject to BLOCK-tier approval gates. |

- Role is declared at session start. If undeclared, the agent operates as **writer**.
- An agent must not invoke a skill outside its role's allowed set.
- Machine-readable role definitions: `config.yaml` → `governance.roles`.

## 14. Autonomy Tiers

Actions are grouped into four tiers that control how much human oversight is required.

| Tier | Actions | Behaviour |
|------|---------|-----------|
| **AUTO** | Read any file; run validation skills (S-23, S-25, S-32, S-01, content-check); run extraction skills (S-34, S-35, S-31, S-37); write reports; generate page plans (S-18) | Proceed without approval. |
| **WARN** | Write content pages (S-19, S-20, S-21, S-26, new-*); update knowledge when < 5 files changed (S-14) | Proceed, but flag `NEEDS_REVIEW` in session log. |
| **BLOCK** | Launch product (S-38 Phase 2+); bulk knowledge update (S-14 with ≥ 5 changed files); exceed session limits; write content when `api_confidence = "medium"` | Pause and request human approval before proceeding. |
| **HUMAN-ONLY** | Modify governance files, skills, or scripts; override hard stops; write content when `api_confidence = "low"`; delete knowledge artifacts | Agent must not attempt. |

Session limits (from `config.yaml` → `governance.session_limits`):
- `max_pages_per_session: 20` — halt and report after 20 content writes
- `max_families_per_session: 3` — escalate if touching more than 3 families
- `max_consecutive_fails: 3` — halt session after 3 consecutive skill failures

## 15. Audit Trail

Every agent session must produce a traceable log.

**Session ID format**: `{YYYY-MM-DD}-{platform}-{role}` (e.g., `2026-03-18-claude-code-writer`)

**Per-action log**: Append to `reports/agents/{session_id}.log`:
```
{ISO-timestamp} {skill_id} {family}/{platform} {result} {duration_ms}
```

**Commit metadata**: Every commit touching `content/` must include (in addition to Section 10 requirements):
```
Agent: {platform}/{role}
Session: {session_id}
```

**Session summary**: On session end, append a final line:
```
{ISO-timestamp} SESSION_END skills_invoked={n} pages_written={n} escalations={n}
```

## 16. File Map

### Content paths

> **Customize the table below for your project.**

| Path | Purpose |
|------|---------|
| `content/docs.aspose.org/en/{family}/{platform}/` | Per-platform documentation pages |
| `content/products.aspose.org/en/{family}/` | Product landing pages |
| `knowledge/{family}/{platform}/model.yaml` | Knowledge model + staleness flag |
| `knowledge/{family}/{platform}/claims.json` | Structured evidence claims |
| `knowledge/{family}/{platform}/claims.md` | Human-readable claim summary |
| `knowledge/{family}/{platform}/api_surface.md` | Public API surface (prose) |
| `knowledge/{family}/{platform}/api_surface.json` | API identifiers + import allowlist |
| `knowledge/{family}/{platform}/snippets/` | Pre-approved code snippets |
| `knowledge/{family}/{platform}/formats.md` | Supported format claims |
| `reports/agents/` | Agent session audit logs |

### Skills reference (30 skills)

| Skill | ID | Purpose |
|-------|----|---------|
| path-guard | S-01 | Enforce allowed write paths |
| project-phase-store | S-10 | Record page creation intent |
| knowledge-diff | S-12 | Detect upstream repo changes |
| stale-detect | S-13 | Identify stale content pages |
| knowledge-update | S-14 | Refresh knowledge model from source |
| embed-knowledge | S-15 | Embed knowledge into vector stores |
| rubric-align | S-17 | Align content to quality rubric |
| page-plan | S-18 | Plan page structure |
| page-draft | S-19 | Draft initial page content |
| page-update | S-20 | Update page after knowledge change |
| page-enhance | S-21 | Enhance page to meet quality bar |
| faq-generate | S-22 | Generate FAQ section |
| ground-check | S-23 | Pre-write evidence verification gate |
| evidence-cite | S-24 | Attach evidence citations |
| eval-page | S-25 | Evaluate page grade (A–F) |
| heal-page | S-26 | Heal low-quality page |
| truth-sync | S-30 | Import external knowledge artifacts |
| truth-index | S-31 | Generate knowledge index |
| content-audit | S-32 | Semantic knowledge verification |
| change-guard | S-33 | Pre-write knowledge gate |
| repo-scout | S-34 | Extract truth from FOSS repository |
| truth-merge | S-35 | Knowledge consolidation with provenance |
| cross-platform | S-36 | Family consistency check |
| corpus-scan | S-37 | Build golden corpus profile |
| launch-product | S-38 | Full FOSS product launch orchestrator |
| content-check | — | Structural content validation |
| new-blog-post | — | Generate blog post |
| new-docs-page | — | Generate documentation page |
| new-kb-howto | — | Generate KB how-to article |
| new-kb-faq | — | Generate KB FAQ page |
| new-reference-page | — | Generate API reference page |

### Skill locations (per agent)

| Agent | Skills path | Instructions file |
|-------|------------|-------------------|
| Claude Code | `.claude/commands/{name}.md` | `CLAUDE.md` |
| Codex CLI | `.agents/skills/{name}/SKILL.md` | `CODEX.md` + `AGENTS.md` |
| Kilo Code | `.kilocode/skills/{name}/SKILL.md` | `.kilocode/rules-code/` |
| Canonical source | `skills/{name}.md` | — |

## 17. README Freshness

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
