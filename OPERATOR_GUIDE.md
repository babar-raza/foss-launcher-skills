<!--
OWNERSHIP: OPERATOR_GUIDE.md
AUTHORITY: Skill concept model and invocation guide
MUST NOT RESTATE: Policy rules — AGENTS.md is the only authority for rules
REVIEW TRIGGERS:
  - AGENTS.md §12 Skill Registry changes (new/renamed skills) → update §3 invocation examples
  - skills/session-start.md changes → update §3 How to Invoke a Skill
MAINTAINED BY: Human maintainer · CI: scripts/ci/check_onboarding_integrity.py
-->
# Operator Guide — aspose.org Content System

This guide explains how to operate the aspose.org content management system for new team
members, maintainers, and anyone inheriting or debugging this system.

---

## §1 — What Is This System?

The aspose.org content system uses AI agents (Claude) to generate, validate, and repair
Aspose FOSS product documentation across five subdomains:
`docs`, `blog`, `kb`, `products`, and `reference`.

Content is grounded in **knowledge models** (per product/platform) that are built from FOSS
source repositories. Every content page must cite evidence from the knowledge model. Quality
is enforced by automated audit, evaluation, and CI gates.

---

## §2 — What Is a "Skill"?

A **skill** is a markdown file in `skills/` (e.g. `skills/knowledge-update.md`). It describes
a procedure that an AI agent follows step by step.

**A skill is NOT a CLI command.** You cannot run a skill from a terminal directly.

| Concept | What it is |
|---------|-----------|
| `skills/knowledge-update.md` | Procedure document for the S-14 skill |
| `/knowledge-update 3d python` | How you invoke it — only inside an AI agent session |
| `scripts/pipeline/refresh_knowledge.py` | The backing script the agent calls automatically |

---

## §3 — How to Invoke a Skill

1. Open a Claude agent session in this repository:
   - Claude Code CLI: run `claude` in the repo root
   - IDE extension: open the repo folder, open the Claude sidebar
2. Type the slash command with arguments:
   ```
   /knowledge-update 3d python
   /launch-product slides java
   /content-check content/docs.aspose.org/en/3d/python/getting-started/installation.md
   /batch-remediate 3d python
   ```
3. The agent reads the skill file and follows the steps. Script-backed steps run automatically.
   Agent-reasoned steps (like reading claims, writing content) are performed by the agent.

---

## §4 — Skills vs Scripts (the CONTRACT model)

Every script-backed skill has a **CONTRACT comment** at the top of the skill file:

```markdown
<!-- CONTRACT: scripts/pipeline/refresh_knowledge.py (runs scout.py + enrich.py + promote.py + index.py)
     postcondition: refresh_knowledge.py executes all 4 pipeline steps
     postcondition: writes merged/pipeline_run.json confirming all 4 steps ran
     note: step 7 (stale flag clear) still requires explicit agent action
-->
```

The CONTRACT tells you:
- **Which script** is called automatically
- **What that script produces** (postconditions)
- **What the agent must do manually** (note: lines)

To find the backing script for any skill: look for the `<!-- CONTRACT: ... -->` block at the
top of the skill file. Skills without a CONTRACT block are fully agent-executed (no script).

---

## §5 — Running Script Steps Manually (When No Agent Is Available)

If you need to run a skill's script portions without an active agent session:

### knowledge-update (S-14)
Runs all 4 knowledge pipeline steps:
```bash
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
repo_path=$(python scripts/pipeline/core/clone_cache.py resolve {family} {platform})
python scripts/pipeline/refresh_knowledge.py {family} {platform} $repo_path
# Confirms completion: check knowledge/{family}/{platform}/merged/pipeline_run.json
```

### content-check (S-32)
```bash
python scripts/pipeline/audit.py {family} {platform}
```

### batch-eval-fix (S-41)
```bash
# Step 1: Evaluate
python -m scripts.pipeline.content_eval evaluate {family} {platform} --format json --remediation
# Step 2: Auto-fix
python scripts/pipeline/remediate.py fix {eval-report-path}
# Step 3: Refresh evidence
python scripts/pipeline/attach_evidence.py --files {modified-files}
```

### truth-audit (S-38)
```bash
python scripts/pipeline/audit.py {family} {platform} --json
```

### translate
```bash
python scripts/translator/cli.py batch {family} {platform} --locales all
```

---

## §6 — Audit FAIL Baseline

Running `python scripts/pipeline/audit.py all` currently shows **0 FAILs** across all 13 products.
All products are clean as of 2026-04-01.

If FAILs appear after a knowledge model update or content generation sprint, check
`reports/audit/baseline-fail-counts.json` for the current documented baseline and root causes.

The CI regression gate (`scripts/ci/check_audit_regression.py`) blocks any PR that introduces
**new** FAILs beyond the documented baseline. Pre-existing baselined FAILs do not block CI.

**Common FAIL root causes:**
| Classification | Root Cause | Fix |
|----------------|-----------|-----|
| `stale_claim_id` | Knowledge model regenerated; claim IDs in content not refreshed | Re-run `attach_evidence.py` or remove stale claim from evidence block |
| `missing_api_member` | Scout didn't extract that member type (e.g., dataclass fields before 2026-04-01 fix) | Update `extraction/api_surface.py` or remove invalid `apis:` entry |
| `content_parse_false_positive` | URL fragment or code comment parsed as API reference | Convert code block to prose or restructure to avoid ambiguity |

If you add new content and see audit FAILs, check whether they are:
1. In the baseline (expected) → no action needed
2. New to a previously-clean product → investigate and fix before merging

---

## §7 — Quick System Health Commands

```bash
# Activate virtual environment first:
source .venv/bin/activate         # Unix
.venv\Scripts\activate            # Windows

# API accuracy audit (24 expected FAILs — see §6)
python scripts/pipeline/audit.py all

# Content quality evaluation for a product
python -m scripts.pipeline.content_eval evaluate 3d python --format json

# Check knowledge model freshness
python scripts/pipeline/project_phase_store.py get 3d python

# Verify skill registry and sync parity
python scripts/ci/check_skill_registry.py
python scripts/pipeline/sync_skills.py --check

# Check for new audit regressions vs baseline
python scripts/ci/check_audit_regression.py audit-results.json reports/audit/baseline-fail-counts.json

# Run all tests
python -m pytest scripts/ -q
```

---

## §8 — Diagnosing Failures

### "UnicodeError" or encoding crash
All pipeline scripts set UTF-8 stdout. If you hit a UnicodeError, check that your Python
environment uses UTF-8 locale. On Windows: set `PYTHONUTF8=1` or use `.venv/Scripts/python`.

### Audit reports unexpected FAILs
1. Check if the FAIL product is in the baseline: `cat reports/audit/baseline-fail-counts.json`
2. If new FAIL in a clean product: run `/diagnose-skill-failure` in an agent session
3. If stale claim IDs: re-run `attach_evidence.py` for the affected product
4. If missing API member: re-run `refresh_knowledge.py` (knowledge model may be stale)

### Knowledge model is stale
1. Check `knowledge/{family}/{platform}/merged/model.yaml` → `stale_since` field
2. If not null: run `/knowledge-update {family} {platform}` or manually run the 4 steps (see §5)

### Pre-commit hook is not running
Install hooks with the single-command installer:
```bash
bash scripts/install-hooks.sh
```
This installs all 3 hooks (pre-commit, commit-msg, post-commit) and verifies installation.

### Skill fails mid-execution
Use S-67 (/diagnose-skill-failure) in an agent session. It classifies failures into:
CONFIG / DATA / CODE / GOVERNANCE / REGRESSION with a resolution path for each.

### CI check fails locally but passes in GitHub Actions (or vice versa)
The local simulation mirrors CI step-for-step. Run:
```bash
bash scripts/ci/simulate_pr_checks.sh
```
If results differ, check that `simulate_pr_checks.sh` was last synchronized with
`content-audit.yml` (both files include a "SYNC" comment with the sync date).

---

## §9 — DAR: Skill Dependency Rules

The DAR (Dependency Activation Rules) table in AGENTS.md §6a defines which skills must run
before others. For example, `/knowledge-bootstrap` must pass before any content generation.

**Before invoking any content-generating skill:** read `reports/phase_state.json` for the
current product and verify required upstream checkpoints are set. If missing, run the
upstream skill first.

DAR compliance is currently enforced by agent instruction-following. The checkpoint store
at `reports/phase_state.json` records which stages have been completed.

---

## §10 — Files and Directories at a Glance

| Path | Purpose |
|------|---------|
| `skills/` | Canonical skill files (source of truth) |
| `.claude/commands/` | Claude Code mirror of skills |
| `.agents/skills/` | Codex CLI mirror of skills |
| `.kilocode/skills/` | Kilo Code mirror of skills |
| `knowledge/{family}/{platform}/` | Knowledge models per product |
| `knowledge/{family}/{platform}/merged/model.yaml` | Model metadata, stale_since |
| `knowledge/{family}/{platform}/merged/claims.json` | Factual claims |
| `knowledge/{family}/{platform}/merged/api_surface.json` | API surface |
| `knowledge/{family}/{platform}/merged/pipeline_run.json` | Confirms full 4-step pipeline ran |
| `reports/audit/` | Audit results and baseline |
| `reports/content_eval/` | Content evaluation reports |
| `reports/proofs/` | CI proof bundles |
| `reports/skill-runs/` | Skill execution records |
| `scripts/pipeline/` | Core pipeline scripts |
| `scripts/ci/` | CI gate scripts |
| `AGENTS.md` | Canonical governance (read this first) |
| `RUNBOOK.md` | CLI quick-reference for operators |
