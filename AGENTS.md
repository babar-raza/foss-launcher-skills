# AGENTS.md — Aspose.org Content Generation & Maintenance Governance

> Last updated: 2026-03-17
> Authority: Human maintainer only (see Section 4 — this file is in the forbidden write list)

## 1. Purpose

Agents operating on this repo generate and maintain documentation for Aspose FOSS products.
All content must be grounded in evidence from the knowledge model. This file is the
authoritative source of operating rules for all agents.

## 2. Read Order (always read in this order before doing any work)

1. This file (AGENTS.md)
2. Agent instructions file (`CLAUDE.md`, `CODEX.md`, or `.kilocode/rules-code/`) — if present
3. `knowledge/{family}/{platform}/model.yaml` — for the target product
4. `knowledge/{family}/{platform}/claims.md` — verify claims are current
5. `knowledge/{family}/{platform}/api_surface.md` — for API grounding

## 3. Mental Model Refresh Protocol

Before editing any content page for family/platform X:

1. Read `knowledge/{family}/{platform}/model.yaml`
2. If `stale_since` is not null → the knowledge model is outdated; do not edit content until
   a knowledge-diff (S-12) and knowledge-update (S-14) have been run
3. Read `claims.md` and `api_surface.md` for the product
4. Only then proceed to content tasks

## 4. Allowed Write Paths (enforced by S-01 path-guard)

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

## 5. Evidence Requirements (non-negotiable)

- Every content page write must pass S-23 (ground-check) before committing
- Every code block in `content/` must come from a snippet in `knowledge/{family}/{platform}/snippets/`
- Every factual claim must be traceable to a `claim_id` in `knowledge/{family}/{platform}/claims.json`
- Claims with `confidence < 0.5` or `claim_source = "llm_fallback"` require human review before use
- Citation comments `<!-- evidence: claim_id={id} source={file} confidence={score} -->` must be
  present in every content page (added by S-24 citation-attach)

## 6. Skill Chains by Task

### Initial generation (new page)

```
S-10 (project phase_store) → S-18 (page-plan) → S-19 (page-draft) → S-22 (faq-generate)
→ S-23 (ground-check) → S-24 (citation-attach) → S-01 (path-guard) → write
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

## 7. Hard Stop Conditions

The following always cause immediate halt (no agent override):

- S-01 path-guard returns `DENY`
- S-23 ground-check returns `FAIL` after 2 retries
- `knowledge/model.yaml.api_confidence = "low"`
- `knowledge/claims.md` has `claim_source=llm_fallback` rate > 50%
- Page grade = F (critical finding) from S-25

## 8. Escalation Conditions (route to human review)

- S-23 `FAIL` persists after remediation
- S-12 diff reveals removed public class or changed method signature
- `stale_report` shows > 30% of page claims are orphaned
- Heal loop (S-26) fails to improve grade after 2 attempts

## 9. Maintenance Workflow

**Trigger**: `knowledge/model.yaml.stale_since` is not null (repo has changed)

1. S-12 (diff) — identify which files changed
2. S-13 (stale-detect) — which content pages are affected
3. For each affected page: S-14 → S-20 → S-25
4. S-15 (sync-vector) — sync vector store if used
5. Commit: `knowledge/` changes + `content/` changes together

## 10. Evidence Proof in Commits

Every commit touching `content/` MUST include in the commit message:

- Knowledge model SHA: `knowledge/{family}/{platform}/model.yaml` `repo_sha` value
- Ground-check result: `PASS` (with report path)
- Skills invoked: `[S-xx, S-yy, ...]`

Citation comments in pages are the inline persistent evidence.

## 11. Prohibited Actions

- Copy content from `golden/` corpus into `content/` pages (`golden/` is rubric reference only)
- Write API method names not present in `knowledge/{family}/{platform}/api_surface.md`
- Write format claims not present in `knowledge/{family}/{platform}/formats.md`
- Generate code blocks using LLM — all code must come from `snippets/`
- Skip S-23 ground-check for any reason
- Write to forbidden paths listed in Section 4

## 12. File Map

### Content paths

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

### Skills reference

| Skill | ID | Purpose |
|-------|----|---------|
| path-guard | S-01 | Enforce allowed write paths |
| knowledge-diff | S-12 | Detect upstream repo changes |
| stale-detect | S-13 | Identify stale content pages |
| knowledge-update | S-14 | Refresh knowledge model from source |
| sync-vector | S-15 | Sync vector store for retrieval |
| rubric-align | S-17 | Align content to quality rubric |
| page-plan | S-18 | Plan page structure |
| page-draft | S-19 | Draft initial page content |
| page-update | S-20 | Update page after knowledge change |
| page-enhance | S-21 | Enhance page to meet quality bar |
| faq-generate | S-22 | Generate FAQ section |
| ground-check | S-23 | Pre-write safety gate |
| citation-attach | S-24 | Attach evidence citations |
| eval-page | S-25 | Evaluate page grade |
| heal-page | S-26 | Heal low-quality page |
| truth-sync | S-30 | Import FOSS-Launcher knowledge |
| truth-index | S-31 | Generate knowledge index |
| content-audit | S-32 | Semantic knowledge verification |
| change-guard | S-33 | Pre-write knowledge gate |
| repo-scout | S-34 | Extract truth from FOSS repository |
| truth-merge | S-35 | Dual-source verification merge |
| cross-platform | S-36 | Family consistency check |

### Skill locations (per agent)

| Agent | Skills path | Instructions file |
|-------|------------|-------------------|
| Claude Code | `.claude/commands/{name}.md` | `CLAUDE.md` |
| Codex CLI | `.agents/skills/{name}/SKILL.md` | `CODEX.md` + `AGENTS.md` |
| Kilo Code | `.kilocode/skills/{name}/SKILL.md` | `.kilocode/rules-code/` |
| Canonical source | `skills/{name}.md` | — |
