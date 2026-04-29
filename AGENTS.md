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
| §4 | [Allowed Write Paths](#4-allowed-write-paths-enforced-by-s-01-path-guard) | → [docs/governance/write-boundaries.md](docs/governance/write-boundaries.md) |
| §4b | [Python File Placement](#4b-python-file-placement-rules) | → [docs/governance/python-placement.md](docs/governance/python-placement.md) |
| §4c | [Content Filename Conventions](#4c-content-filename-conventions-tc-new-01-enforced-2026-04-25) | → [docs/governance/write-boundaries.md](docs/governance/write-boundaries.md) |
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
| §10 | [Evidence Proof in Commits](#10-evidence-proof-in-commits) | → [docs/governance/evidence-and-provenance.md](docs/governance/evidence-and-provenance.md) |
| §10a | [Verification Standards](#10a-verification-standards-for-fixes) | → [docs/governance/evidence-and-provenance.md](docs/governance/evidence-and-provenance.md) |
| §10b | [Content Provenance Rules](#10b-content-provenance-rules) | → [docs/governance/provenance-rules.md](docs/governance/provenance-rules.md) |
| §10c | [Output-Location Discipline](#10c-output-location-discipline) | → [docs/governance/evidence-and-provenance.md](docs/governance/evidence-and-provenance.md) |
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
  CI simulation, knowledge pipeline, skill execution, content generation
  or validation

Does NOT apply to:
- GitHub Actions CI: runs on ubuntu-latest (native bash); no Windows
  enforcement needed or permitted in CI configuration
- Linux/macOS contributors: already native bash; no change
- Read-only operations (browsing files, reading docs): no shell requirement

### Accepted shell (Windows)
Git Bash (Git for Windows) is the only accepted shell on Windows.
Detection signature: `$MSYSTEM` contains "MINGW" AND `$BASH_VERSION` is set.
Installation: https://git-scm.com/downloads

### Rejected shells (Windows) — hard failures in block mode
- **cmd.exe**: No bash, no Unix utilities, wrong path separators
- **PowerShell / pwsh**: Different quoting, no Unix utilities, CRLF risk
- **WSL (any version)**: Drops environment variables across the Windows->WSL
  boundary, breaking governance hooks. Documented failure mode:
  `docs/STATUS-venv-closure.md`. Permanently rejected.
- **Cygwin**: MSYS2-incompatible path semantics. Rejected.
- **Any other bash-on-Windows** that does not set `$MSYSTEM=MINGW*`: rejected.

### Enforcement
Phase 1+2 (warn mode): Violations print a warning to stderr and continue.
Phase 4+ (block mode): Violations exit non-zero and prevent execution.
Detection utility: `scripts/ci/check_shell_bash.sh`
Entry points enforced: `install-hooks.sh`, `pre-commit-audit.sh`,
  `check_venv_bash_hook.sh` (agent PreToolUse hook)

### Exceptions
There are no runtime bypass mechanisms in block mode.
In warn mode, all invocations proceed regardless of shell.
If an exception is genuinely required (e.g., unusual CI migration),
the human maintainer must temporarily revert to warn mode via a code
change (not an env var), document the reason, and restore block mode
after the exception window closes.

### Ownership
Human maintainer owns this policy. Scripts are operator-maintained.

## 3. Mental Model Refresh Protocol

> Full detail: [docs/workflows/mental-model-refresh.md](docs/workflows/mental-model-refresh.md)

## 3a. Platform Folder Naming

> Full detail: [docs/governance/naming-conventions.md](docs/governance/naming-conventions.md)

## 3b. `plugin_platform` Display Name (products.aspose.org)

> Full detail: [docs/governance/naming-conventions.md](docs/governance/naming-conventions.md)

## 4. Allowed Write Paths (enforced by S-01 path-guard)

> Full detail: [docs/governance/write-boundaries.md](docs/governance/write-boundaries.md)

## 4b. Python File Placement Rules

> Full detail: [docs/governance/python-placement.md](docs/governance/python-placement.md)

## 4c. Content Filename Conventions (TC-NEW-01, enforced 2026-04-25)

> Full detail: [docs/governance/write-boundaries.md](docs/governance/write-boundaries.md)

## 5. Evidence Requirements (non-negotiable)

- Every content page write must pass S-23 (content-check) before committing.
  **S-23 implementation**: `python scripts/pipeline/audit.py --files {path}` (deterministic, scriptable).
  Pre-commit hook enforces this automatically; CI workflow blocks PRs with FAILs.
- Every code block in `content/` must come from a snippet in `knowledge/{family}/{platform}/snippets/`
- Every factual claim must be traceable to a `claim_id` in `knowledge/{family}/{platform}/claims.json`
- Claims with `confidence < 0.5` require human review before use
- An `evidence:` YAML frontmatter block must be present in every content page. Generate it
  deterministically with `python scripts/pipeline/attach_evidence.py --files {path}` (for pages
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
python scripts/pipeline/site_planner.py {family} {platform} --replan-blog
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

> Full detail: [docs/governance/launch-gates.md](docs/governance/launch-gates.md)

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

> Full detail: [docs/governance/evidence-and-provenance.md](docs/governance/evidence-and-provenance.md)

## 10a. Verification Standards for Fixes

> Full detail: [docs/governance/evidence-and-provenance.md](docs/governance/evidence-and-provenance.md)

## 10b. Content Provenance Rules

> Full detail: [docs/governance/provenance-rules.md](docs/governance/provenance-rules.md)

## 10c. Output-Location Discipline

> Full detail: [docs/governance/evidence-and-provenance.md](docs/governance/evidence-and-provenance.md)

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

## 12. File Map

### Content paths

| Path | Purpose |
|------|---------|
| `content/docs.aspose.org/en/{family}/{platform}/` | Per-platform documentation pages |
| `content/products.aspose.org/en/{family}/` | Family landing page (layout: `family`) — `/family-sync` |
| `content/products.aspose.org/en/{family}/{platform}/` | Platform product page (layout: `plugin`) — `/new-products-page` |
| `knowledge/{family}/{platform}/merged/model.yaml` | Knowledge model + staleness flag |
| `knowledge/{family}/{platform}/merged/claims.json` | Structured evidence claims |
| `knowledge/{family}/{platform}/merged/api_surface.md` | Public API surface — human-readable (generated by promote.py) |
| `knowledge/{family}/{platform}/merged/api_surface.json` | API identifiers + import allowlist |
| `knowledge/{family}/{platform}/snippets/` | Pre-approved code snippets |
| `knowledge/{family}/{platform}/formats.md` | Supported format claims |

### Environment & Dependencies

**Rule: all scripts must load environment variables exclusively from `.env` via `core.env_loader`.**

#### Virtual environment (.venv)

**Rule: always use the repo `.venv` Python directly. Never use system Python for normal repo work.**

**DR-01 policy (enforced by hooks):**
- Use the `.venv` Python binary by **direct path** — do not rely on activation or `PATH`.
- Do not trust `$VIRTUAL_ENV` as proof that the correct Python is active — it reflects shell state, not binary health.
- Activation failure is not `.venv` failure. If the shell cannot activate but `.venv/Scripts/python` exists, use it directly.
- If the `.venv` Python binary cannot start, use the approved repair script (see below). Do not fall back to system Python.

**Invoke Python (in Bash tool commands):**
```bash
# Windows (Git Bash)
.venv/Scripts/python scripts/pipeline/my_script.py

# Unix / macOS
.venv/bin/python scripts/pipeline/my_script.py
```

**Install packages through .venv Python (not bare pip):**
```bash
# Windows
.venv/Scripts/python -m pip install <package>

# Unix / macOS
.venv/bin/python -m pip install <package>
```

**Check whether a package is already installed:**
```bash
.venv/Scripts/python -m pip show <package>   # Windows
.venv/bin/python -m pip show <package>        # Unix / macOS
```

**Activation (optional, for human operator convenience only):**
```bash
# Windows (Git Bash)
source .venv/Scripts/activate

# Unix / macOS
source .venv/bin/activate
```
Activation is not required for agent skill chains. It is a shell convenience for interactive sessions. Skill chains must use explicit `.venv` paths regardless of activation state.

**If `.venv` is broken or missing — approved repair path:**
```bash
bash scripts/ci/repair_venv.sh          # repair in place
bash scripts/ci/repair_venv.sh --fresh  # delete and recreate
```
The repair script uses system Python **only** for `python -m venv .venv` (the bootstrap exception). All subsequent operations use the newly created `.venv` Python.

**Diagnose .venv health:**
```bash
.venv/Scripts/python scripts/ci/venv_doctor.py          # human-readable
.venv/Scripts/python scripts/ci/venv_doctor.py --json   # machine-readable
```

#### `.env` file (repo root)

The single source of truth for all runtime configuration. It is **git-ignored** — never commit it. Copy `.env.example` (repo root) to `.env` and fill in values.

Key variables:

| Variable | Used by | Required? |
|----------|---------|-----------|
| `GITHUB_TOKEN` | `update_product_registry.py` | Optional (or `--token` arg) |
| `ASPOSE_CLONE_CACHE` | all pipeline scripts | Optional — defaults to `runs/.clone_cache/` |
| `PROFESSIONALIZE_API_KEY` | `llm_router.py` (used by `enrich.py`, `gap-eval/run.py`, `fix_spec.py`, `synthesize.py`) | Optional — falls back to Ollama |
| `LLM_API_KEY` | `translator/cli.py` | **Required** for translation |
| `LLM_API_BASE_URL` | `translator/cli.py` | Optional — defaults to `https://llm.professionalize.com/v1` |
| `TRANSLATE_PRIMARY_MODEL` | `translator/cli.py` | Optional — defaults to `gpt-oss` |
| `TRANSLATE_BULK_MODEL` | `translator/cli.py` | Optional — defaults to `TRANSLATE_PRIMARY_MODEL` |
| `TRANSLATE_OLLAMA_BASE_URL` | `translator/backends/ollama.py` | Optional — defaults to `http://localhost:11434` |
| `TRANSLATE_OLLAMA_MODEL` | `translator/backends/ollama.py` | Optional — defaults to `llama3.2` |
| `GOOGLE_API_KEY` | `seo/get_keywords.py`, `seo/review_keywords.py` | Optional (SEO only) |
| `LITELLM_KEY` | `seo/pipeline/recommend.py` | Optional (SEO only) |

#### `env_loader` — automatic dotenv loading

`scripts/pipeline/core/env_loader.py` provides `load_env()`. Every CLI entry point calls it once at startup, before any `os.environ.get()` call:

```python
from core.env_loader import load_env
load_env()
```

Behaviour:
- Reads `.env` at repo root into `os.environ`
- Uses `override=False` — shell-exported variables and CI secrets always take precedence
- No-op (silent) if `python-dotenv` is not installed or `.env` does not exist

**Agents must not** call `os.environ.get()` without first ensuring `load_env()` has been called in the entry point. For new scripts, add the standard two-line block immediately after the `sys.path` setup section.

#### Dependency installation

Each subdirectory under `scripts/` maintains its own `requirements.txt`. Install only what you need:

```bash
pip install -r scripts/pipeline/requirements.txt    # core pipeline (includes python-dotenv)
pip install -r scripts/translator/requirements.txt  # translator subsystem
pip install -r scripts/gap-eval/requirements.txt    # gap-eval runner
pip install -r scripts/seo/requirements.txt         # optional — SEO scripts only
pip install -r scripts/generator/requirements.txt   # reference page generator
pip install -r scripts/ci/requirements.txt          # CI check scripts
pip install -r scripts/maintenance/requirements.txt # maintenance utilities
```

`scripts/requirements.txt` is a navigation index only — do not `pip install -r` it directly.

### Scripts reference

| Path | Purpose |
|------|---------|
| `scripts/pipeline/core/env_loader.py` | `load_env()` — loads `.env` from repo root via python-dotenv; `override=False`; no-op if dotenv absent |
| `scripts/pipeline/llm_router.py` | Shared LLM routing: professionalize.com → Ollama fallback. `EndpointStatus` enum, `CallResult` dataclass. CLI: `--probe`. |
| `scripts/pipeline/llm_registry.yaml` | Single source of truth for LLM endpoint URLs, models, dimensions, timeouts. |
| `scripts/pipeline/verification/` | Clean re-export namespace over `token_ops.py`; provides `extract_tokens`, `verify_tokens` under more descriptive import paths (`from verification.extractor import extract_tokens`, `from verification.verifier import verify_tokens`). `token_ops.py` remains unchanged and both import paths work simultaneously. |

### Skills reference

| Skill | ID | Purpose |
|-------|----|---------|
| path-guard | S-01 | Enforce allowed write paths |
| project-phase-store | S-10 | Track generation phase state for a product (reads/writes reports/phase_state.json) |
| knowledge-diff | S-12 | Detect upstream repo changes |
| stale-detect | S-13 | Identify stale content pages |
| knowledge-update | S-14 | Refresh knowledge model from source |
| embed-knowledge | S-15 | Embed knowledge artifacts into dual vector stores (three-tier: professionalize.com → Ollama → TF-IDF) |
| rubric-align | S-17 | Align content to quality rubric |
| page-plan | S-18 | Plan page structure |
| page-draft | S-19 | Draft initial page content |
| page-update | S-20 | Update page after knowledge change |
| page-enhance | S-21 | Enhance page to meet quality bar |
| faq-generate | S-22 | Generate FAQ section |
| content-check | S-23 | Pre-write structural and quality check gate |
| evidence-cite | S-24 | Attach knowledge citations to content pages |
| eval-page | S-25 | Evaluate page grade |
| heal-page | S-26 | Heal low-quality page |
| truth-index | S-31 | Generate knowledge index |
| content-audit | S-32 | Semantic knowledge verification |
| change-guard | S-33 | Pre-write knowledge gate |
| repo-scout | S-34 | Extract truth from FOSS repository |
| truth-merge | S-35 | Promote scout + enriched claims into merged/ |
| cross-platform | S-36 | Family consistency check |
| knowledge-enrich | S-37 | LLM-enriched claims from scout api_surface (bounded-description mode). enrich.py returns False on total LLM failure (all providers unreachable) — do not proceed to S-35. `--no-llm` is the only path that writes empty `enriched_claims.json` and returns True. |
| truth-audit | S-38 | Member-level API verification (deep) |
| batch-remediate | S-40 | Full eval→fix→LLM→re-eval pipeline for all content pages of a product |
| batch-eval-fix | S-41 | Lightweight eval + deterministic auto-fixes only; no LLM pass; safe for unattended runs |
| category-fix | S-42 | Run a specific fixer on files by category code (ST, RV, EG, RL, AA, PC, FC, PT, CP, CG) |
| gap-eval | S-43 | Content verification against clone cache — publishability verdict. `Tier3Result` dataclass replaces `_TIER3_UNAVAILABLE` sentinel; three failure modes now distinguishable: `NOT_CONFIGURED`, `INTENTIONAL_SKIP` (no source context — data problem, not LLM), `UNREACHABLE`/`AUTH_FAILED`. Finding JSON includes `endpoint_status` and `endpoint_used` fields. |
| gap-plan | S-44 | Wave-ordered remediation planning from gap-eval findings |
| gap-report | S-45 | Cross-product gap synthesis report |
| gap-apply | S-46 | Execute wave-ordered fix specs from gap-plan output (Wave 1 auto-fix, Wave 2 LLM-planned substitutions, Wave 3 page generation, Wave 4 human escalation) |
| site-plan | S-47 | Production-grade pre-generation site manifest (deterministic YAML output) |
| family-sync | S-48 | Update family-level products page to reflect all launched platforms |
| launch-product | S-49 | 5-subdomain full documentation launch orchestrator (10 stages) |
| content-eval | S-51 | Multi-dimensional content evaluation (16 evaluators, grading, batch mode) |
| translate-page | S-52 | Translate a single English content page to target locales |
| translate-batch | S-53 | Batch translate all pages for a family/platform to target locales |
| knowledge-bootstrap | S-54 | Pre-condition gate; detects and resolves stale knowledge before content or validation commands |
| no-downgrade-guard | S-55 | Pre-write quality comparison to prevent content regression *(internal sub-routine — called by generation skills before write; not invoked directly by users)* |
| new-docs-page | S-56 | Generate documentation pages for docs.aspose.org |
| new-blog-post | S-57 | Generate blog posts for blog.aspose.org |
| new-kb-howto | S-58 | Generate KB how-to articles |
| new-kb-faq | S-59 | Generate or update FAQ page for a product platform |
| new-reference-page | S-60 | Generate API reference pages for reference.aspose.org |
| new-products-page | S-61 | Generate products.aspose.org landing pages |
| batch-reference | S-62 | Bulk reference page generation for all missing classes/enums; idempotent |
| code-smoke | S-63 | Syntax and type-check Python code blocks in content files |
| getting-started | S-64 | Fresh-clone onboarding: install deps, configure env, bootstrap knowledge, verify |
| link-validate | S-65 | Validate cross-subdomain internal links in content files; report BROKEN links where the target slug does not exist locally |
| register-human-content | S-66 | Onboard a human-authored page into quality and provenance systems (sets auto_updatable: false, attaches evidence, assigns grade baseline) |
| diagnose-skill-failure | S-67 | Governed diagnostic procedure when a skill or pipeline script fails; classifies failure as CONFIG/DATA/CODE/GOVERNANCE and produces a breakage report |
| update-registry | S-68 | Scan all 26 aspose-{family}-foss GitHub orgs, discover FOSS repos, and write data/products.json (supports --dry-run, --local-only, --force) |
| new-kb-index | S-69 | Scaffold KB platform section landing page |
| new-docs-index | S-70 | Scaffold Docs platform section landing page |
| new-reference-index | S-71 | Scaffold Reference platform section landing page |
| evidence-repair | S-72 | Repair evidence frontmatter for validator-blocked pages (P-03 or audit FAIL); evidence-frontmatter-only; never modifies body content; fail-closed; supports --dry-run |
| manual-edit | S-73 | Operator-directed targeted content edit: applies a human-specified targeted change (frontmatter, wording, code block, section rewrite) to a single file under full path-guard, evidence, provenance, and audit trail governance; revert-on-failure; single file per invocation |
| causal-backtrack | S-74 | Resolve upstream dependency failures: given evaluation findings with cause_class UPSTREAM_MISSING or BAD_LINK_FORMAT, classifies dependency root cause, invokes S-62/S-60 for missing targets or S-73 for wrong-URL fixes, and writes cause-classification.json + dependency-verification.json evidence; supports --dry-run |
| locale-patch | S-75 | Propagate targeted text fixes to locale translation copies of a fixed English source file; dry-run first; applies (old_text, new_text) patches to all locale variants; emits patch_report.md; never re-translates whole page |
| commit | S-76 | Full commit-prep workflow: inspect working tree, categorize changes, plan 2–8 Conventional Commits, handle override tokens for protected paths, add invoked-skill IDs to content commits, stage precisely (never git add -A), verify quality gates (pytest), create commits with structured bodies, clean up post-commit token lifecycle, print final summary |
| session-start | S-77 | Mandatory session initialization gate: read AGENTS.md + CLAUDE.md in full, confirm §2 Read Order and §6b capability assessment method, output SESSION GATE PASSED block before accepting any task |
| evidence-enhance | S-78 | Improve section evidence coverage on pages that already pass validation (audit.py PASS, grade A/B); thin wrapper around attach_evidence.py --force; evidence-frontmatter-only; never modifies body content; pre-flight audit required; revert-on-failure; use S-72 for validator-blocked pages |
| launch-rollback | S-79 | Revert one product's generated content files to last committed git state without touching system files (scripts/, .agents/, reports/, knowledge/); reads site_plan.yaml for file list; dry-run manifest first; backs `scripts/pipeline/launch_rollback.py` |
| coverage-reconcile | S-80 | Trace every knowledge unit (claim, API member) to a page disposition (used_in_content / excluded_by_planner / orphaned); writes `reports/coverage/{family}/{platform}/{date}-coverage-report.md`; backs `scripts/pipeline/knowledge_coverage.py` |
| knowledge-coverage-audit | S-81 | Per-claim disposition table: maps every claim in merged/claims.json to exactly one disposition (USED_EVIDENCE / SURFACE_ONLY / EXCLUDED_THRESHOLD / EXCLUDED_TIER / ORPHANED); writes `reports/coverage/{family}/{platform}/knowledge_coverage.json` and `.md`; backs `scripts/pipeline/knowledge_coverage.py` |
| delta-site-plan | S-82 | Incremental site planning after knowledge update: runs `site_planner.py --mode update` to compute pages_to_add, pages_to_update, pages_to_remove, pages_renamed; writes delta section to site_plan.yaml; requires knowledge_delta.json from S-14 |
| page-retire | S-83 | Retire obsolete content pages via `draft: true` + `retired_at` frontmatter (Hugo standard); never deletes files; dual-signal retirement rule (cluster + claim signal); --dry-run first; backs `scripts/pipeline/retire_page.py` |
| refresh-product | S-84 | Full post-launch product refresh orchestration: 16-step chain from S-12 (detect) through S-14, S-82, **Step 3.5 PIA** (page_impact_assess.py), S-20, delta-dispatch, S-83, S-62 --update, S-48, S-23, S-65, S-53, **Step 13.5 coverage-report** (refresh_review.py), verification gate (post_refresh_verify --verify including Check 6 coverage completeness), and S-76 (commit); early-exit if no SHA change; post-conditions: `reports/refresh_review/{family}/{platform}/page_decisions.json` covers all 5 subdomains + `coverage_report.md` shows all subdomains assessed |
| truth-audit-content | S-85 | Line-level content truth audit against clone cache and knowledge model (read-only; decomposes pages into units, verifies each, produces gap ledger); backs `scripts/pipeline/truth_audit_content.py` |
| refresh-product-page | S-86 | Re-generate a single products.aspose.org landing page through the full S-61 pipeline with no-downgrade-guard protection; use when S-61 template has been improved and existing pages should benefit |
| system-heal | S-87 | Audit-driven content healing: deterministic baseline (--no-llm) → extended baseline (LLM + tier3_cache) → origin classification (origin_map.py) → content healing (S-74/S-46/S-26 by route) → pipeline evidence report → re-verify → commit or escalate; 8-phase; max 50 findings (use S-44+S-46 above that); AMBIGUOUS and tier3_non_determinism_flag findings never auto-repaired; backs `scripts/gap-eval/origin_map.py` + `scripts/gap-eval/tier3_cache.py` |
| backlog | S-88 | Unified backlog management and planning: view briefing, automated plan scanning (with `.claude/plans/` repo-affinity filtering), add items (with intake dedup), investigate (intake), investigate-run (execute existing INV item inline — reads brief, gathers evidence, records findings, moves to Resolved), surface (contextual item surfacing — scores backlog against response context, returns top matches; called automatically per §15), remind, session handoff, archive, triage inbox, reconcile (with cross-item analysis), status investigation, plan creation, replan amendment, plan hardening, traceability, governed closeout, merge, group, link, **harvest** (automatic report → backlog intake: extracts open items from qualifying reports via `report_extract.py`, routes through harvest ledger for dedup/state tracking via `harvest_ledger.py`, auto-intakes high-confidence items to inbox, queues low-confidence for review; primary trigger: report finalization by S-87/S-76; secondary: `/backlog update` step 1b; safety net: `/session-start` step 6 advisory + `/backlog reconcile` step 8d); all state in `backlog/` + `plans/from_backlog/` (gitignored); 23 subcommands |
| heal-batch | S-89 | Batch healing from content_eval report: routes findings through heal policy table to auto/llm/regen modes in a single pass; auto-mode applies deterministic fixers; llm-mode emits S-26 invocation descriptors; regen-mode emits causal-backtrack descriptors with `regen_after` flags; optional before/after verification with regression detection; supersedes deterministic portion of S-40 (batch-remediate); backs `scripts/pipeline/remediate.py heal` |
| publish-readiness-review | S-90 | Agent-executed governed inspection — replaces all "human-review" dead-ends with bounded inspection, judgment, skill routing, re-verification, and verdict; reads audit context, classifies pages (PUBLISH-READY / NEEDS-ACTION / ACCEPTABLE-GRADE-C / STRUCTURAL-GAP / BLOCKED), routes to S-21/S-26/batch-reference/S-65/S-38/S-73/S-74; H-gate equivalents for H-01..H-05; writes inspection-manifest.json + action-log.json + final-verdict.md; supports --scope, --triage-unknowns, --dry-run; backs `skills/publish-readiness-review.md` |
| plan-normalize | S-91 | Execution-safe plan quality gate — classifies every section of a plan (historical-reference / verified-current-state / completed-archive / open-actionable / operator-guidance / design-rationale / intentionally-omitted), verifies claims against current repo state, extracts only still-open work, marks each item ready/blocked/stale/already-done/needs-replan, selects single next executable item, blocks execution on ambiguous sections or unverified capabilities; modes: assess (verdict only), amend (writes exec-pack sibling or edits in-place), launch (assess + amend + execute first safe item); mandatory gate before executing inherited, long, amended, or archive-containing plans; backs `skills/plan-normalize.md` |
| triage-confirm | S-92 | Layer 2 body-prose staleness scanner for the refresh pipeline — complements Layer 1 SHA-based detection (refresh_knowledge.py) by scanning page body prose for references to API classes or knowledge claims that have changed or been removed; returns stale/current verdict with per-finding reasons; invoked by S-84 (refresh-product) Step 9.5 and S-89 (heal-batch) triage phase; backs `scripts/pipeline/triage_confirm.py` + `scripts/pipeline/reconcile_triage.py`; skill file: `skills/triage_confirm.md` |
| repo-patrol | S-93 | Discover new FOSS repos across 26 GitHub orgs, score confidence, and produce `reports/discovery/patrol_report.json`; default dry-run (no registry changes); `--apply` adds candidates to `data/products.json` with `status: candidate`; `--inactive-days` threshold (default 180); `--force` re-evaluates rejected repos; backs `scripts/pipeline/repo_patrol.py scan`; skill file: `skills/repo-patrol.md` |
| change-sweep | S-94 | Batch SHA comparison across all active launched products in `data/products.json`; reads `knowledge/{family}/{platform}/merged/model.yaml` stored SHA, updates clones, classifies impact HIGH/MEDIUM/LOW; produces `reports/discovery/sweep_report.json`; read-only (does NOT set `stale_since` — S-12's job); backs `scripts/pipeline/repo_patrol.py sweep`; skill file: `skills/change-sweep.md` |
| discovery-triage | S-95 | Route patrol and sweep reports to backlog actions — reads `reports/discovery/patrol_report.json` + `sweep_report.json`, creates backlog items per §9 decision trees; **MVP: NEVER directly invokes S-12 or S-84** — all findings route to backlog items only; direct auto-refresh gated behind TC-GATE-01 post-pilot; backs `skills/discovery-triage.md` |
| section-enhance | S-96 | Inventory a target content section across any subdomain, detect gaps against clone-cache and knowledge truth, and generate a read-only proposal pack; Phase 1 is proposal-only (zero writes to `content/`); accepts any plausible target input form, resolves to canonical repo path recording all alias corrections; backs `skills/section-enhance.md` |

**S-43 (gap-eval) CLI flags:**
- `--deterministic` — Exhaustive Stage 2 + no LLM (Tier 1 + Tier 2 only). Fully reproducible. Recommended for regression tracking and CI integration.
- `--seed N` — Random seed for Stage 2 sampling (default: 42). Only used when `--max-stage2-entries > 0`.
- `--max-stage2-entries N` — Stage 2 entries to check: 0 = all entries (default, exhaustive); N > 0 = sample N entries.
- `--no-tier3-cache` — Bypass Tier 3 result cache; force fresh LLM calls for all Tier 3 findings;
  write results back to cache after evaluation. Use when suspecting cache staleness or testing
  Tier 3 behavior. **Performance ceiling:** for products with > 50 content files, a full
  `--no-tier3-cache` run requires one LLM call per Tier 3 finding and typically exceeds 5 minutes
  (may time out in CI with default 2-min limits). Use `--deterministic` for CI and reserve
  `--no-tier3-cache` for targeted local diagnosis. (Added with S-87/tier3_cache.py.)

### Enforcement scripts

| Script | Purpose |
|--------|---------|
| `scripts/pipeline/audit.py` | Deterministic S-23 content-check: verifies every API token in content against `api_surface.json` |
| `scripts/pre-commit-audit.sh` | Pre-commit hook — blocks commits with API accuracy FAILs |
| `.github/workflows/content-audit.yml` | CI — blocks PRs with API accuracy FAILs |
| `scripts/pipeline/content_eval/` | Multi-dimensional content evaluation (16 evaluators); run via `python scripts/pipeline/run_content_eval.py evaluate {family} {platform}` (no PYTHONPATH needed) or `python -m content_eval ...` from `scripts/pipeline/`. DEFAULT_EVALUATORS = 9 (fast/deterministic); ALL_EVALUATORS = 16. |
| `scripts/pipeline/run_content_eval.py` | Wrapper entrypoint for content_eval — invoke from repo root without any PYTHONPATH prefix. Use this instead of `PYTHONPATH=scripts/pipeline python -m content_eval`. |
| `scripts/pipeline/batch_reference.py` | Backing script for S-62 (batch-reference) — generates template-based reference pages from api_surface.json for headless/CI runs. CLI: `python scripts/pipeline/batch_reference.py {family} {platform} [--kind class\|enum\|all] [--limit N] [--dry-run]`. |
| `scripts/pipeline/refresh_knowledge.py` | Runs the full knowledge pipeline (scout→enrich→promote→index), auto-clears `stale_since` in `merged/model.yaml` after successful refresh, and writes `merged/knowledge_delta.json` with semantic diff. CLI: `python scripts/pipeline/refresh_knowledge.py {family} {platform} [--no-auto-fetch] [--check-only]`. |
| `scripts/pipeline/retire_page.py` | Retire content pages via `draft: true` + `retired_at` frontmatter (Hugo standard); backs S-83 (page-retire). CLI: `python scripts/pipeline/retire_page.py {file-path} [--dry-run]` or `--from-plan {site_plan_path}`. |
| `scripts/pipeline/post_refresh_verify.py` | Post-refresh verification gate and progress tracker; backs S-84 (refresh-product). CLI: `python scripts/pipeline/post_refresh_verify.py {family} {platform} --step {name}` / `--verify` / `--status`. |
| `scripts/ci/check_skill_readme_coverage.py` | Documentation coverage: asserts README.md exists in all four skill trees (skills/, .claude/commands/, .agents/skills/, .kilocode/skills/) and root README.md links to skills. **Blocking** (no continue-on-error). |

Usage:
```
python scripts/pipeline/audit.py slides python       # Single product
python scripts/pipeline/audit.py all                  # All products
python scripts/pipeline/audit.py --files path1.md     # Specific files (pre-commit)
python scripts/pipeline/audit.py all --json           # Machine-readable output
```

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

### Skill locations (per agent)

| Agent | Skills path | Instructions file |
|-------|------------|-------------------|
| Claude Code | `.claude/commands/{name}.md` | `CLAUDE.md` |
| Codex CLI | `.agents/skills/{name}/SKILL.md` | `CODEX.md` + `AGENTS.md` |
| Kilo Code | `.kilocode/skills/{name}/SKILL.md` | `.kilocode/rules-code/` |
| Canonical source | `skills/{name}.md` | — |

Each tree has a `README.md` at its root describing its contents, invocation syntax, and any divergence from canonical. See [`skills/README.md`](skills/README.md) for the primary catalog.

#### Internal skills (auto-invoked sub-routines)

The following 8 skills exist in canonical `skills/` and in `.agents/` and `.kilocode/` trees, but are **intentionally absent from `.claude/commands/`**. They are auto-invoked by other skills and are never called directly by users or agents.

| Slug | ID | Role |
|------|----|------|
| `knowledge-bootstrap` | S-54 | Pre-condition gate before content or validation commands |
| `evidence-cite` | S-24 | Attaches knowledge citations; auto-invoked by generation skills |
| `path-guard` | S-01 | Enforces allowed write paths; auto-invoked on every write |
| `change-guard` | S-33 | Pre-write knowledge gate; auto-invoked before content writes |
| `no-downgrade-guard` | S-55 | Pre-write quality comparison sub-routine |
| `rubric-align` | S-17 | Sub-evaluator called by eval-page |
| `gap-plan` | S-44 | Planning sub-tool for the remediation pipeline |
| `project-phase-store` | S-10 | Checkpoint infrastructure |

Source: `scripts/pipeline/sync_skills.py:INTERNAL_SKILLS`.

#### Claude Code-only extras (not registered skills)

The following files exist **only in `.claude/commands/`**. They are not registered in §12, have no file in canonical `skills/`, and are not present in `.agents/` or `.kilocode/` trees.

| File | Role |
|------|------|
| `translate.md` | Dispatcher: routes to `/translate-page` (S-52) or `/translate-batch` (S-53) based on argument type. Convenience wrapper; adds no new capability. |
| `seo-review.md` | Interactive human review gate for SEO recommendations. Claude Code utility; not yet a registered skill. |

Source: `scripts/pipeline/sync_skills.py:KNOWN_EXCEPTIONS`.

---

## 14. Completion Verification Protocol

> Full detail: [docs/workflows/completion-verification.md](docs/workflows/completion-verification.md)

## 16. Testing Seam Contract — Tiered Monkeypatch Policy

> Full detail: [docs/governance/testing-seam-contract.md](docs/governance/testing-seam-contract.md)

## Operating Standard

Every agent operating on this repository is expected to behave as a disciplined user of a governed skill system — not as an autonomous reasoner inventing its own processes. The skill system is the documented, human-reviewed record of how content work is done here. When skills cover a requirement, they must be used. When they do not, the gap must be reported and recorded so the skill system can grow. An agent that silently bypasses skills, fabricates workflows, or completes tasks partially without disclosure violates the operating contract of this repository regardless of whether the output appears correct. Correctness of output does not retroactively legitimize non-compliant process. The test is not "did it work?" — the test is "did it work through the skill system, with the skill system's evidence and path rules intact?"
