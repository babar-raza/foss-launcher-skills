# AGENTS.md — Aspose.org Content Generation & Maintenance Governance

> Last updated: 2026-04-28 (governance refactor — sections decomposed to docs/governance/ and docs/workflows/ child documents; see routing matrix below)
> Authority: Human maintainer only (see Section 4 — this file is in the forbidden write list)

<details>
<summary>Section Index (click to expand)</summary>

| § | Section | Key content |
|---|---------|-------------|
| §1 | [Purpose](#1-purpose) | What agents do here |
| §2 | [Read Order](#2-read-order-always-read-in-this-order-before-doing-any-work) | Mandatory pre-work gate |
| §2a | [Source-of-Truth Hierarchy](#2a-source-of-truth-hierarchy) | Conflict resolution |
| §2b | [Shell Execution Policy](#2b-shell-execution-policy-windows-local-operations) | Windows shell rule |
| §3 | [Mental Model Refresh](#3-mental-model-refresh-protocol) | → [docs/workflows/mental-model-refresh.md](docs/workflows/mental-model-refresh.md) |
| §4 | [Allowed Write Paths](#4-allowed-write-paths-enforced-by-s-01-path-guard) | → [docs/reference/governance-gates.md](docs/reference/governance-gates.md) |
| §4b | [Python File Placement](#4b-python-file-placement-rules) | → [docs/development/python-placement.md](docs/development/python-placement.md) |
| §4c | [Content Filename Conventions](#4c-content-filename-conventions-tc-new-01-enforced-2026-04-25) | → [docs/reference/governance-gates.md](docs/reference/governance-gates.md) |
| §5 | [Evidence Requirements](#5-evidence-requirements-non-negotiable) | Non-negotiable grounding |
| §6 | [Skill Chains by Task](#6-skill-chains-by-task) | → [docs/workflows/skill-chains.md](docs/workflows/skill-chains.md) |
| §6a | [Skill-First Mandate](#6a-skill-first-execution-mandate) | → [docs/governance/dar-table.md](docs/governance/dar-table.md) |
| §6b | [Gap Escalation](#6b-capability-classification-and-gap-escalation) | → [docs/workflows/gap-escalation.md](docs/workflows/gap-escalation.md) |
| §6c | [Causal Backtracking](#6c-causal-backtracking-protocol-added-2026-04-03) | → [docs/workflows/causal-backtracking.md](docs/workflows/causal-backtracking.md) |
| §6f | [Blog Slug Governance](#6f-blog-slug-governance-added-2026-04-08) | Blog URL rules |
| §7 | [Hard Stop Conditions](#7-hard-stop-conditions) | When to halt |
| §7a | [Launch-Readiness Gates](#7a-launch-readiness-gates) | Pre-launch requirements |
| §7b | [Human-Review Risk Tiers](#7b-human-review-risk-tiers) | Risk tiers + S-90 requirements |
| §7c | [Agent-Executed Governed Inspection](#7c-agent-executed-governed-inspection-canonical-interpretation-of-human-review) | Canonical meaning of "human-review" |
| §8 | [Escalation Conditions](#8-escalation-conditions-invoke-s-90-first-escalate-to-real-human-only-for-these) | S-90 routing + real escalation conditions |
| §9 | [Maintenance Workflow](#9-maintenance-workflow) | → [docs/workflows/maintenance.md](docs/workflows/maintenance.md) |
| §9a | [Evaluator Change Checklist](#9a-evaluator-change-checklist) | → [docs/workflows/evaluator-changes.md](docs/workflows/evaluator-changes.md) |
| §9b | [Regeneration Triggers](#9b-regeneration-after-extraction-script-changes) | → [docs/workflows/change-trigger-matrix.md](docs/workflows/change-trigger-matrix.md) |
| §9c | [Change-Trigger Matrix](#9c-change-trigger-matrix) | → [docs/workflows/change-trigger-matrix.md](docs/workflows/change-trigger-matrix.md) |
| §10 | [Evidence Proof in Commits](#10-evidence-proof-in-commits) | → [docs/_archive/pre-refactor/governance/evidence-and-provenance.md](docs/_archive/pre-refactor/governance/evidence-and-provenance.md) |
| §10a | [Verification Standards](#10a-verification-standards-for-fixes) | → [docs/_archive/pre-refactor/governance/evidence-and-provenance.md](docs/_archive/pre-refactor/governance/evidence-and-provenance.md) |
| §10b | [Content Provenance Rules](#10b-content-provenance-rules) | → [docs/_archive/pre-refactor/governance/provenance-rules.md](docs/_archive/pre-refactor/governance/provenance-rules.md) |
| §10c | [Output-Location Discipline](#10c-output-location-discipline) | → [docs/_archive/pre-refactor/governance/evidence-and-provenance.md](docs/_archive/pre-refactor/governance/evidence-and-provenance.md) |
| §11 | [Prohibited Actions](#11-prohibited-actions) | Hard prohibitions |
| §12 | [File Map](#12-file-map) | All scripts, skills, paths |
| §13 | [Internal Metadata Policy](#13-internal-metadata-rendering-policy) | Evidence panel hiding |
| §14 | [Completion Verification](#14-completion-verification-protocol) | → [docs/workflows/completion-verification.md](docs/workflows/completion-verification.md) |

</details>

## 1. Purpose

Agents operating on this repo generate and maintain documentation for Aspose FOSS products. All content must be grounded in evidence from the knowledge model. This file is the authoritative source of operating rules for all agents.

## 2. Read Order (always read in this order before doing any work)

1. This file (AGENTS.md)
2. Agent instructions file (`CLAUDE.md`, `CODEX.md`, or `.kilocode/rules-code/`) — if present
3. `knowledge/{family}/{platform}/merged/model.yaml` — for the target product
4. `knowledge/{family}/{platform}/merged/claims.json` — verify claims are current
5. `knowledge/{family}/{platform}/merged/api_surface.md` — for API grounding (human-readable, generated by promote.py)
6. Before creating any new `.py` file in `scripts/pipeline/`, read `scripts/pipeline/PIPELINE.md`
   in full (§ New File Protocol, § Registry Schema, § Shared Module Rules).

New contributor or agent? See the `getting-started` skill for step-by-step fresh-clone setup.

> **New operator or agent?** Before reading further, start here:
> - [`docs/QUICKSTART.md`](docs/QUICKSTART.md) — 30-minute onboarding (environment, session flow, five workflows)
> - [`OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) — What skills are and how to invoke them
> - [`RUNBOOK.md`](RUNBOOK.md) — Terminal command cheatsheet
>
> After completing the quickstart, return here and read AGENTS.md in full before your first content task.

## 2a. Source-of-Truth Hierarchy

When a conflict exists between two artifacts, this hierarchy governs which one is authoritative. Higher items in the list override lower items — never the reverse.

| Priority | Source | Scope |
|----------|--------|-------|
| 1 | FOSS repo source code (clone cache at `runs/.clone_cache/`) | API surface, class names, method signatures, namespaces |
| 2 | `knowledge/{family}/{platform}/merged/api_surface.json` | What the scout extracted from source; authoritative for content generation |
| 3 | `knowledge/{family}/{platform}/merged/formats.json` | Format support; must reconcile with api_surface (see §9c) |
| 4 | `knowledge/{family}/{platform}/merged/claims.json` | Enriched semantic claims; must not contradict api_surface or formats |
| 5 | `knowledge/{family}/{platform}/merged/limitations.md` | Known unimplemented features; overrides positive claims at same priority level |
| 6 | Generated content in `content/` | Output artifact; must reflect all higher sources |

**Conflict resolution rule**: When a content claim contradicts a higher-priority source, fix the content (or the knowledge artifact) — never demote the higher-priority source to match the content.

**Cloned repos are read-only.** Agents never write to `runs/.clone_cache/`. The scout (S-34) reads them; the knowledge layer synthesizes from them.

**Phase artifacts are not source of truth.** `knowledge/{family}/{platform}/scout/` and `knowledge/{family}/{platform}/merged/` are derived from the clone cache. If they contradict the clone cache, re-run the knowledge bootstrap (S-12 → S-14) to regenerate from source.

## 2b. Shell Execution Policy (Windows Local Operations)

### Git Push — Non-Interactive Token Auth

The GCM credential dialog does not open in agent Bash sessions (no TTY).
Use `GH_TOKEN` (always set in the environment) with the `x-access-token` URL scheme:

```bash
git push "https://x-access-token:${GH_TOKEN}@github.com/Aspose/aspose.org.git" main
```

Note: `GITHUB_PAT` is also set but does **not** work for push to this repo — only `GH_TOKEN` does.
The remote URL in `.git/config` uses lowercase `aspose` but GitHub redirects to `Aspose`; both work.

### Rule
All local repo operations on Windows MUST be performed in Git Bash
(MSYS2/MINGW64, provided by Git for Windows). This is not a preference —
the governance scripts, hooks, and pipeline depend on bash semantics and
Unix utilities (grep, git, bash conditionals, LF line endings).

### Scope
Applies to:
- Human operators running scripts, hooks, or pipeline commands locally
- Agent-driven workflows using the Claude Code Bash tool on Windows
- Any script invoked during: setup, hook installation, git commit,

> Full detail on invocations,  policy, and repair steps: [docs/registries/file-map.md](docs/registries/file-map.md)

## 3. Mental Model Refresh Protocol

> Full detail: [docs/workflows/mental-model-refresh.md](docs/workflows/mental-model-refresh.md)

- **Filesystem hygiene check**: At session start, run `ls | grep '^public-'` in the repo root to detect stale Hugo build artifact directories. If any exist (e.g., `public-sq-*`, `public-as-*`, `public-iv-*`), delete them with `rm -rf <dirname>`. These dirs are gitignored and do not affect `git status`, but waste disk space and may confuse rendered validation scans. Do NOT delete `public/` (Hugo default output, used by `hugo server`).

## 3a. Platform Folder Naming

> Full detail: [docs/_archive/pre-refactor/governance/naming-conventions.md](docs/_archive/pre-refactor/governance/naming-conventions.md) *(archived)*

## 3b. `plugin_platform` Display Name (products.aspose.org)

> Full detail: [docs/_archive/pre-refactor/governance/naming-conventions.md](docs/_archive/pre-refactor/governance/naming-conventions.md) *(archived)*

## 4. Allowed Write Paths (enforced by S-01 path-guard)

> Full detail: [docs/reference/governance-gates.md](docs/reference/governance-gates.md)

## 4b. Python File Placement Rules

> Full detail: [docs/development/python-placement.md](docs/development/python-placement.md)

## 4c. Content Filename Conventions (TC-NEW-01, enforced 2026-04-25)

> Full detail: [docs/reference/governance-gates.md](docs/reference/governance-gates.md)

## 5. Evidence Requirements (non-negotiable)

- Every content page write must pass S-23 (content-check) before committing.
  **S-23 implementation**: `python scripts/pipeline/commands/content/audit.py --files {path}` (deterministic, scriptable).
  Pre-commit hook enforces this automatically; CI workflow blocks PRs with FAILs.
- Every code block in `content/` must come from a snippet in `knowledge/{family}/{platform}/snippets/`
- Every factual claim must be traceable to a `claim_id` in `knowledge/{family}/{platform}/claims.json`
- Claims with `confidence < 0.5` require human review before use
- An `evidence:` YAML frontmatter block must be present in every content page. Generate it
  deterministically with `python scripts/pipeline/commands/healing/attach_evidence.py --files {path}` (for pages
  with code blocks) or manually via S-24 (evidence-cite, for prose-only pages). Format:
  ```yaml
  evidence:
    model_sha: "<repo_sha from merged/model.yaml>"   # anchors to knowledge version
    model_version: "<version>"
    claims: [CLM-xxx, ...]      # claim_ids from merged/claims.json ([] is valid)
    apis: [ClassName.method, …] # verified against merged/api_surface.json ([] is valid)
    formats: [{ext: glb, support: both}, …]  # omit if no format content
  ```
  Do **not** include `ground_check:` — it is self-reported and unverifiable.
  Do **not** use inline HTML comments (`<!-- evidence: ... -->`).
  Frontmatter is the canonical citation store, machine-validated by `audit.py`. The
  `evidence-panel` Hugo partial renders this data **only in non-production builds**
  (see Section 13 — Internal Metadata Rendering Policy). After any knowledge model update,
  rerun `attach_evidence.py {family} {platform}` to refresh stale blocks.

## 5a. Knowledge Bootstrap Prerequisite (LH-02, added 2026-04-30)

**Knowledge bootstrap is a hard prerequisite for content generation and healing.**

These rules were adopted after the forensic-audit-healing sprint (2026-04-30) confirmed that
15 of 16 products had no local knowledge, causing content to be generated or evaluated without
any grounded source to validate against.

### Generation gate

- `/launch-product`, `/new-docs-page`, `/new-blog-post`, `/new-kb-howto`, `/batch-reference`,
  and all generation skills MUST verify that `knowledge/{family}/{platform}/merged/model.yaml`
  exists and `stale_since == null` before writing any content page.
- If knowledge is missing: HARD STOP. Run `/repo-scout`, `/truth-merge` first.
- If knowledge is stale: HARD STOP. Run `/knowledge-diff`, `/knowledge-update` first.
- `batch_reference.py` MUST NOT gracefully degrade on missing knowledge. It must exit with
  error code 1 before writing any pages when `knowledge.available == False`.

### Evaluator gate

- All content evaluators MUST NOT silently return empty findings when knowledge is unavailable.
- When `knowledge.available == False`, every evaluator MUST return exactly one WARN finding
  with the text: "UNVERIFIED: knowledge artifacts not available for {family}/{platform}. Claims
  cannot be validated."
- Silent skip (returning `[]`) is prohibited -- it causes ungrounded content to pass quality gates.

### Ungrounded content marking

- Content pages generated or evaluated without local knowledge MUST have
  `provenance.knowledge_status: ungrounded` in their frontmatter.
- Ungrounded pages MUST NOT receive grade A. The grade ceiling for ungrounded pages is B.
- Publication readiness review (S-90) MUST fail or produce a WARN when a product has
  ungrounded pages in any mandatory content section (docs, kb, blog, reference).

### Verification

These rules are enforced by:
- `scripts/pipeline/tests/content_eval/test_evaluators.py`: `test_no_knowledge_warn()`
  asserts evaluators return WARN with "UNVERIFIED" on missing knowledge (added STATE 1.5)
- `scripts/pipeline/tests/test_batch_reference.py`: `test_stale_knowledge_exits` asserts
  batch_reference exits non-zero when knowledge is stale (covers EH-02 behavior; missing
  model.yaml path added to same exit code path in STATE 1.5)
- `audit.py`: will FAIL pages with `knowledge_status: ungrounded` that have grade A

## 6. Skill Chains by Task

> Full detail: [docs/workflows/skill-chains.md](docs/workflows/skill-chains.md)

## 6a. Skill-First Execution Mandate

> Full detail: [docs/governance/dar-table.md](docs/governance/dar-table.md)

## 6b. Capability Classification and Gap Escalation

> Full detail: [docs/workflows/gap-escalation.md](docs/workflows/gap-escalation.md)

## 6c. Causal Backtracking Protocol (added 2026-04-03)

> Full detail: [docs/workflows/causal-backtracking.md](docs/workflows/causal-backtracking.md)

### §6f Blog Slug Governance (added 2026-04-08)

**Features post slug (Post 2, weight 2, mandatory) MUST be cluster-derived.**
`plan_blog()` in `site_planner.py` derives the Post 2 slug from the highest-claim-count
non-limitations knowledge cluster. The pattern `{family}-key-features-{platform}` is
**banned for `source: derived`**; the validator raises `ValueError` at plan generation time
if it appears on a derived record.

**Existing posts are protected by default.** Any existing post with a `*-key-features-*`
slug is preserved as `source: discovered` on every normal re-plan. These slugs are NEVER
overridden automatically — doing so would break deployed URLs without a redirect strategy.

**Migration path (opt-in only).** To replace a legacy features slug with a cluster-derived
one, a human must explicitly run:
```bash
python scripts/pipeline/commands/launch/site_planner.py {family} {platform} --replan-blog
```
This flag may only be invoked by a human operator with deliberate intent. It MUST NOT be
called automatically from `/launch-product`, `/refresh-product`, or any orchestration skill.
After `--replan-blog` is used, the plan's `sections.blog.pages_to_retire` list will contain
the old post path — run `/page-retire {family} {platform} {old_slug}` immediately for the
replaced post before committing.

**`auto_updatable: false` is an unconditional block.** A blog post with `auto_updatable: false`
in its frontmatter provenance block was authored or edited by a human. Even with `--replan-blog`,
its slug is never overridden. Do not set `auto_updatable: false` on skill-generated content.

**Traceability fields.** All mandatory blog post records in `site_plan.yaml` include:
- `blog_role: announcement | features | deep-dive` — identifies the post's function
- `cluster: {category}` — present on `features` and `deep-dive` records; identifies the
  knowledge cluster that determined the slug

These fields are consumed by `/new-blog-post` to scope content correctly. Do not strip them.

## 7. Hard Stop Conditions

The following always cause immediate halt (no agent override):

- S-01 path-guard returns `DENY`
- S-23 content-check returns `FAIL` after 2 retries
- `knowledge/model.yaml.api_confidence = "low"`
- Page grade = F (critical finding) from S-25
- Agent classifies requirement as NONE (no skill covers it) and proceeds with ad hoc work —
  unconditional STOP; produce a gap escalation report (§6b) instead
- A required upstream skill (per DAR table in §6a) returns `STOP` or `DENY` — do not
  proceed to the downstream skill; report the blocking condition to the user

### Blog Content Governance (added 2026-04-03)

**Hard stop: manual blog file creation is PROHIBITED.**

- Blog files MUST be created exclusively via the `/new-blog-post` skill (S-57).
- Manual file creation (writing directly to `content/blog.aspose.org/` without the
  skill) bypasses all of: no-downgrade-guard (S-55), `attach_evidence.py`,
  change-guard (S-33), and the pre-commit API audit.
- Any file where `provenance.content_origin: unknown` AND `author != "Aspose"` is a
  rogue-path indicator. DO NOT commit it without manual evidence remediation and
  explicit human review.
- Blog posts MUST use the directory structure: `{slug}/index.md`. Flat `.md` leaf files
  are rejected by pre-commit (`check-blog-slugs.py` P-05 check).
- `aliases:` lists MUST NOT contain path segments starting with `test` (`check-blog-slugs.py`
  P-06 check).
- `evidence.claims` and `evidence.apis` MUST be non-empty before commit
  (`validate_frontmatter.py` P-03/P-04 checks). Files with
  `content_origin: manual-remediation` are temporarily exempt.

## 7a. Launch-Readiness Gates

> Full detail: [docs/_archive/pre-refactor/governance/launch-gates.md](docs/_archive/pre-refactor/governance/launch-gates.md) *(archived)*

## 7b. Human-Review Risk Tiers

All generated content is classified into risk tiers. Higher tiers require S-90 governed
inspection before publication; real human escalation only per §7c.

| Tier | Content type | Review requirement | Examples |
|------|--------------|--------------------|---------|
| **Tier 1** | Code-heavy reference pages, blog posts with format tables, capability claims | S-90 (`/publish-readiness-review`) review gate — agent executes H-01..H-05 equivalents (§7a); real human escalation only per §7c conditions | `slides/net` reference pages, blog posts with `## Supported Formats` sections |
| **Tier 2** | Docs pages, KB how-to articles, FAQ pages | S-90 spot-check (`--scope docs` or `--scope kb`; `--grade-filter C,D,F`) | `docs/getting-started`, `kb/how-to-*` |
| **Tier 3** | Locale files, pure structural pages (index/_index), products landing pages | Automated gates only; S-90 optional | `_index.md` files, locale translations, products pages |

**Tier 1 classification triggers** (any one is sufficient):
- Page contains a format support table (markdown table with Import/Export or Read/Write columns)
- Page contains code blocks with real API calls (not just install snippets)
- Page makes a capability claim (e.g., "supports conversion", "can export to PDF")
- Page is a blog post (all blog posts are Tier 1)

**When tiers matter**: Before a product launch, run S-90 on Tier 1 and Tier 2 content. Tier 3
proceeds on automated gates alone. After EVALUATOR_LOGIC_VERSION bump, re-evaluate Tier 1 first,
then run S-90 to classify and route any newly failing pages.

## 7c. Agent-Executed Governed Inspection (canonical interpretation of "human-review")

> **Added 2026-04-17** — operationalizes all "human-review" language in the system.

When any skill, plan, report, or governance section says **"human-review required"**,
**"human action required"**, **"manual review"**, **"manual investigation"**,
**"needs reviewer"**, or any equivalent phrase, interpret it as follows:

> **NOT**: "Stop and wait for a person."
> **MEANS**: "Invoke S-90 (`/publish-readiness-review`) — the agent performs the bounded
> inspection, makes judgment calls, routes to fix skills, re-verifies, and emits an
> evidence-backed verdict."

**Agents MUST invoke S-90 rather than halting when:**
- A grade report or audit verdict describes content as "ready for review"
- A skill's escalation path says "escalate to human review" (S-26, S-46 Wave 4, etc.)
- H-gates H-01 through H-05 are listed as required before launch (§7a)
- A policy note says a finding "requires human triage" (e.g., UNKNOWN_CLASS WARNs in §9a)
- A pipeline evidence report lists "human action required" items (S-87 Phase 5)

**Escalation to a real human is still required only when:**
1. Grade F after 2 S-26 passes + 1 S-89 batch pass with no improvement
2. PIPELINE-bucket finding from S-87 (skill breakage, extraction failure, pipeline misconfiguration)
3. `tier3_non_determinism_flag: true` findings (evaluator non-determinism — agent cannot trust them)
4. Legal, license, or business claims requiring external verification
5. S-23 `FAIL` persists after full remediation (existing §8 condition 1)
6. S-12 diff reveals removed public class or changed method signature (existing §8 condition 2)

**For all other cases, S-90 is the governed execution path.** Do not halt and write an
escalation item where S-90 can perform the inspection. The distinction between "inspection"
(agent-executable) and "escalation" (truly external dependency) is governed by this section.

## 8. Escalation Conditions (invoke S-90 first; escalate to real human only for these)

> **Updated 2026-04-17** — agents must invoke S-90 (`/publish-readiness-review`) before
> escalating. S-90 will classify which items need real human escalation and which it can
> resolve. The conditions below are the only ones that produce real human escalation output
> from S-90.

- S-23 `FAIL` persists after full remediation by S-90 (S-90 condition 5)
- S-12 diff reveals removed public class or changed method signature (S-90 condition 6)
- `stale_report` shows > 30% of page claims orphaned — run S-90; if still failing after
  S-26 passes, escalate
- Heal loop (S-26) fails to improve grade after 2 attempts AND S-89 batch pass also fails —
  escalate with S-90 evidence record (S-90 condition 1)
- Skill breakage report is filed (§6b) — a broken skill cannot be bypassed; human must
  diagnose and repair the skill before affected task types can proceed (S-90 condition 2)

## 9. Maintenance Workflow

> Full detail: [docs/workflows/maintenance.md](docs/workflows/maintenance.md)

## 9a. Evaluator Change Checklist

> Full detail: [docs/workflows/evaluator-changes.md](docs/workflows/evaluator-changes.md)

## 9b. Regeneration After Extraction Script Changes

> Full detail: [docs/workflows/change-trigger-matrix.md](docs/workflows/change-trigger-matrix.md)

## 9c. Change-Trigger Matrix

> Full detail: [docs/workflows/change-trigger-matrix.md](docs/workflows/change-trigger-matrix.md)

## 10. Evidence Proof in Commits

> Full detail: [docs/_archive/pre-refactor/governance/evidence-and-provenance.md](docs/_archive/pre-refactor/governance/evidence-and-provenance.md) *(archived)*

## 10a. Verification Standards for Fixes

> Full detail: [docs/_archive/pre-refactor/governance/evidence-and-provenance.md](docs/_archive/pre-refactor/governance/evidence-and-provenance.md) *(archived)*

## 10b. Content Provenance Rules

> Full detail: [docs/_archive/pre-refactor/governance/provenance-rules.md](docs/_archive/pre-refactor/governance/provenance-rules.md) *(archived)*

## 10c. Output-Location Discipline

> Full detail: [docs/_archive/pre-refactor/governance/evidence-and-provenance.md](docs/_archive/pre-refactor/governance/evidence-and-provenance.md) *(archived)*

## 11. Prohibited Actions

- Copy content from `golden/` corpus into `content/` pages (`golden/` is rubric reference only)
- Write API method names not present in `knowledge/{family}/{platform}/merged/api_surface.md`
- Write format claims not present in `knowledge/{family}/{platform}/formats.md`
- Generate code blocks using LLM — all code must come from `snippets/`
- Skip S-23 content-check for any reason
- Write to forbidden paths listed in Section 4
- Bypass a registered skill by performing its equivalent function through manual reasoning,
  inline shell commands, or ad hoc prompting — even if the output appears correct
- Perform a targeted content edit — wording change, frontmatter update, code block replacement,
  or section rewrite — on any content file without invoking S-73 (manual-edit). This applies
  regardless of the size of the change. A one-word typo fix is still subject to S-73's
  path-guard and post-edit validation. "It's just a small change" is not an exemption.
- Perform any step of a requirement classified as PARTIAL or NONE without first producing a
  gap escalation report (§6b) and receiving explicit human approval for the uncovered portion
- Invent a new workflow or process for a requirement type not covered by §6 — produce the
  gap escalation report and enhancement plan defined in §6b instead, then halt
- Classify work as "forensic", "ad-hoc", "diagnostic", "manual", "one-off",
  "operator-directed", or any other label to imply exemption from skill-first
  execution (§6a). All work falls under the skill system or gap escalation (§6b).
  There is no third category.
- Set, recommend setting, or reference any SKIP_* environment variable. Bypass
  variables are operator-only infrastructure not accessible to agents.
- Proceed with PARTIAL or NONE capability without producing a gap escalation
  report and halting for human approval. Claiming "operator direction" does not
  substitute for gap escalation when no matching skill exists.
- **Clone cache canonical location (anti-regression)**: The FOSS clone cache lives
  exclusively at `runs/.clone_cache/` inside this repo.
  - Windows canonical path: `D:/onedrive/Documents/GitHub/aspose.org/runs/.clone_cache/`
  - Resolver: `scripts/pipeline/core/clone_cache.py` → `cache_root()` (checks `ASPOSE_CLONE_CACHE`
    env var first, then defaults to `<repo-root>/runs/.clone_cache/`)
  - `ASPOSE_CLONE_CACHE` may override the default, but must not point to any `foss-launcher` path.
    If it does, the resolver will fail with an error.
  - **Prohibited**: searching for, inferring, or falling back to any `foss-launcher` clone-cache
    path (`foss-launcher/runs/.clone_cache/`, `../foss-launcher/runs/.clone_cache/`, etc.) <!-- HISTORICAL_OBSOLETE_FOSS_LAUNCHER_REFERENCE: prohibition example, not an active instruction -->
  - **Prohibited**: treating a `foss-launcher` sibling directory as clone cache
  - If clone cache resolution fails, inspect `scripts/pipeline/core/clone_cache.py` and
    `runs/.clone_cache/` — never look in obsolete `foss-launcher` paths.
  - Any plan, prompt, memory entry, or documentation that presents `foss-launcher` as the current
    clone-cache location is invalid and must be corrected before use.
- Commit a `.md` file whose sole staged diff from HEAD is a changed `graded_at:` timestamp. The pre-commit hook Step 10 auto-reverts such files; using `--no-verify` to bypass this gate is prohibited.
- **No `hugo -d <relative-path>` from the Bash tool.** All agent Hugo builds must write to a system temp dir (`$(mktemp -d)` in bash, `tempfile.mkdtemp()` in Python subprocesses). Any relative destination (including patterns like `public-as-*`, `public-iv-*`, `public-sq-*`, or any other `public-<suffix>` name) writes full-site HTML artifacts into the repo root, bloating git status and risking accidental commits. **Using `SKIP_DESTRUCTIVE_BASH_CHECK=1` to bypass this block is prohibited for agent sessions.** Use `tmpdir=$(mktemp -d)` in Bash or `tempfile.mkdtemp()` in Python instead. Enforcement: PreToolUse Bash hook (`scripts/ci/hooks/check_destructive_bash_hook.sh`). Reference implementation: `scripts/ci/hooks/check_hugo_build.sh`. Rule documentation: `docs/_archive/pre-refactor/governance/write-boundaries.md §Hugo Output Discipline`.

## 12. File Map

> Full detail: [docs/registries/file-map.md](docs/registries/file-map.md) (content paths, environment, scripts reference)
> Skills registry: [docs/registries/skills.md](docs/registries/skills.md)

### Content paths

> Full detail: [docs/registries/file-map.md](docs/registries/file-map.md)

### Environment & Dependencies

> Full detail: [docs/registries/file-map.md](docs/registries/file-map.md)

### Scripts reference

> Full detail: [docs/registries/file-map.md](docs/registries/file-map.md)

### Skills reference

> Full detail: [docs/registries/skills.md](docs/registries/skills.md)

### Enforcement scripts

> Full detail: [docs/registries/skills.md](docs/registries/skills.md)

## 13. Internal Metadata Rendering Policy

The `evidence:` frontmatter block is **internal provenance data** that must never appear on the public-facing website. It exists solely for pipeline validation and debugging.

### Design

The `layouts/partials/evidence-panel.html` partial is gated in all four public-facing theme base templates (`products`, `docs`, `kb`, `blog`) with:

```html
{{- if ne hugo.Environment "production" }}{{- partial "evidence-panel.html" . -}}{{- end }}
```

This means:

| Build context | `hugo.Environment` | Panel renders? |
|--------------|-------------------|----------------|
| CI production build (`--environment production`) | `"production"` | **No** |
| CI staging build (`--environment staging`) | `"staging"` | Yes (QA only) |
| Local `hugo server` | `"development"` | Yes (dev only) |
| Plain local `hugo` (no `--environment` flag) | `"production"` (default) | **No** |

### CI workflow requirement

All site build workflows in `aspose.org-workflows` **must** pass `--environment "${{ github.event.inputs.environment }}"` to the `hugo` build command. This ensures the `workflow_dispatch` `environment` input (already used for deploy targeting) is also forwarded to Hugo's template context. All 7 site workflows already do this.

If a new site workflow is added, the same flag is required on the `hugo` build step. Omitting it is safe (Hugo defaults to `"production"` → panel hidden) but must be explicit.

### What must not change

- The `evidence:` frontmatter block must remain in content files — it is required by
  `audit.py`, `attach_evidence.py`, and `evidence_depth.py` for validation and staleness
  detection. Do not remove or relocate it.
- Do not call `evidence-panel.html` unconditionally from any base template. The partial
  itself contains a comment warning against this.
- Do not gate the panel on URL patterns (e.g. `-qa.aspose.org`) — the `hugo.Environment`
  mechanism is the correct and durable approach.

---


## 14. Completion Verification Protocol

> Full detail: [docs/workflows/completion-verification.md](docs/workflows/completion-verification.md)

## 15. Metrics Obligation

All workflows and pipeline commands that call `llm.professionalize.com` — directly or
through `LLMRouter` — carry a mandatory metrics obligation.

**Requirements:**

- Every professionalize HTTP call must be captured as a `MetricsEvent` using the approved
  infrastructure: `ProfessionalizeClient`, `LLMRouter`, or a registered adapter entry in
  `scripts/pipeline/config/metrics_callsite_registry.yaml`.
- Each completed work-slice must aggregate captured events into a validated `MetricsRow`
  (17 fields) via `RunMetrics`, and persist it locally before any submission is attempted.
- New professionalize call sites must be registered in `metrics_callsite_registry.yaml`.
  Unregistered direct calls will fail CI (`check_professionalize_call_sites.py`).
- Default submission mode is dry-run. Production submission requires explicit owner approval
  and both `AGENT_METRICS_ENDPOINT` and `AGENT_METRICS_TOKEN` environment variables set
  locally. Token values must never be committed, printed, or stored in evidence bundles.
- Non-professionalize calls (Gemini, Ollama, M2M, local models) are excluded from
  professionalize `token_usage` and `api_calls_count` metrics. Do not mix them.
- Test rows must use `job_type="test"` and `item_name` prefix `[TEST]`. Maximum 2 per sprint,
  hard limit 3.
- Metrics failures must never crash or block the parent pipeline job.

**Governance scripts:** `scripts/ci/checks/check_professionalize_call_sites.py`,
`check_metrics_taxonomy.py`, `check_metrics_no_secrets.py`,
`check_metrics_test_post_limit.py`, `check_metrics_event_ledger_schema.py`,
`check_metrics_sheet_payload_schema.py`, `check_metrics_docs_propagation.py`.

**Reference:** `METRICS-PLAN-001` (`scripts/pipeline/config/metrics_taxonomy.yaml`,
`metrics_callsite_registry.yaml`).

## 16. Testing Seam Contract — Tiered Monkeypatch Policy

> Full detail: [docs/development/testing-seams.md](docs/development/testing-seams.md) *(moved)*

## Operating Standard

Every agent operating on this repository is expected to behave as a disciplined user of a governed skill system — not as an autonomous reasoner inventing its own processes. The skill system is the documented, human-reviewed record of how content work is done here. When skills cover a requirement, they must be used. When they do not, the gap must be reported and recorded so the skill system can grow. An agent that silently bypasses skills, fabricates workflows, or completes tasks partially without disclosure violates the operating contract of this repository regardless of whether the output appears correct. Correctness of output does not retroactively legitimize non-compliant process. The test is not "did it work?" — the test is "did it work through the skill system, with the skill system's evidence and path rules intact?"
