<!--
OWNERSHIP: RUNBOOK.md
AUTHORITY: Terminal command cheatsheet (script-level commands only)
MUST NOT RESTATE: Policy rules — link to AGENTS.md; never copy governance text
REVIEW TRIGGERS:
  - AGENTS.md §12 venv execution policy changes → update all python command blocks
  - New workflow skills added to AGENTS.md §12 → add matching runbook entry
MAINTAINED BY: Human maintainer · CI: scripts/ci/check_onboarding_integrity.py (Check 5)
-->
# RUNBOOK — Aspose.org Operator Guide

Quick-reference for common operations. For governance rules, see `AGENTS.md`.
New to this system? Read [OPERATOR_GUIDE.md](OPERATOR_GUIDE.md) first — it explains what skills are and how to invoke them.

## Shell Requirement (Windows)

**All local operations on Windows MUST use Git Bash** (MSYS2/MINGW64, from
[Git for Windows](https://git-scm.com/downloads)). WSL, PowerShell, and cmd.exe
are not supported — governance scripts depend on bash semantics and Unix utilities.
WSL is permanently rejected; see `docs/STATUS-venv-closure.md` for the reason.

For the full policy, see `AGENTS.md §2b`. CI runs on `ubuntu-latest` (no Windows
enforcement needed in CI).

## 1. Setup (Fresh Clone)

Run `/getting-started` or follow these steps manually:

```bash
# 1. Activate venv
source .venv/Scripts/activate   # Windows Git Bash
source .venv/bin/activate       # Unix/macOS

# 2. Install dependencies
pip install -r scripts/pipeline/requirements.txt
pip install -r scripts/translator/requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env: set GITHUB_TOKEN, optionally LLM_API_KEY

# 4. Install all hooks (pre-commit, commit-msg, post-commit)
bash scripts/install-hooks.sh

# 5. Populate provenance for pre-existing locale files (required post-clone migration)
# Locale files translated since cdaa1daac already have committed provenance.
# Older locale files that have not been re-translated need this step.
# The script is idempotent — safe to re-run; files with provenance are skipped.
.venv/Scripts/python scripts/pipeline/provenance_backfill.py
# Expected output: "Backfilled N files, skipped M (already have provenance), 0 errors"

# 6. Verify
.venv/Scripts/python scripts/pipeline/audit.py all
```

## 1b. Update Product Registry

Run after a fresh clone (replaces the manual Step 3 in §1) and whenever a new org or repo
is added to GitHub. Writes `data/products.json` — the source of truth for clone URLs used
by `clone_cache.py` and `refresh_knowledge.py`.

```bash
# Skill invocation (recommended)
/update-registry

# Or run the backing script directly
.venv/Scripts/python scripts/pipeline/update_product_registry.py --token $GITHUB_TOKEN
```

**Modes:**

| Command | Behaviour |
|---------|-----------|
| `/update-registry` | Scan all 26 GitHub orgs, merge with knowledge/ dirs, write registry |
| `/update-registry --dry-run` | Preview discovered repos; do NOT write data/products.json |
| `/update-registry --local-only` | Skip GitHub; derive registry from knowledge/ dirs only |
| `/update-registry --force` | Overwrite `active` status for all existing entries |

**Output**: `data/products.json` — one entry per `{family}/{platform}` pair with `repo_url`,
`clone_url`, and `active` flag.

**After discovering new products**: run `/knowledge-bootstrap {family} {platform}` for each
new entry, then `/launch-product {family} {platform}`.

**Troubleshooting**: if `clone_cache.py` reports "clone_url not found", re-run this skill
to refresh the registry before retrying.

## 2. Launch a New Product

```bash
# Step 1: Bootstrap knowledge
/knowledge-bootstrap {family} {platform}

# Step 2: Generate site manifest
.venv/Scripts/python scripts/pipeline/site_planner.py {family} {platform} --dry-run
# Review YAML output, then without --dry-run to write

# Step 3: Generate content (via agent skills)
/launch-product {family} {platform}
# This orchestrates: site-plan -> page generation -> evidence -> audit -> grade

# Step 4: Verify
.venv/Scripts/python scripts/pipeline/audit.py {family} {platform}
python -m scripts.pipeline.content_eval evaluate {family} {platform}
.venv/Scripts/python scripts/pipeline/truth_audit.py {family} {platform}
```

## 3. Refresh Knowledge After Upstream Changes

### 3a. Detect upstream changes (S-12)

```bash
# Check if a product's upstream repo has new commits
/knowledge-diff {family} {platform}
```

This fetches the clone, compares SHAs, and auto-sets `stale_since` in `model.yaml` for HIGH/MEDIUM impact.
If SHAs match, it exits with "no changes" — safe to run on any product at any time.

### 3b. Refresh knowledge model (S-14)

```bash
# Full pipeline: scout → enrich → promote → index
/knowledge-update {family} {platform}

# Or run the backing script directly
.venv/Scripts/python scripts/pipeline/refresh_knowledge.py {family} {platform}
```

After success: `merged/pipeline_run.json` confirms all steps ran, `stale_since` is cleared,
`knowledge_delta.json` is written with the semantic diff (new/removed/modified claims and APIs).

### 3c. Generate delta site plan (S-82)

```bash
/delta-site-plan {family} {platform}
```

Reads `knowledge_delta.json` and produces a `delta:` section in `reports/plans/{family}/{platform}/site_plan.yaml`
with `pages_to_add`, `pages_to_update`, `pages_to_remove`, and `pages_renamed`.

### 3d. Execute downstream content updates

```bash
# Update pages affected by changed claims/APIs
/page-update {family} {platform}

# Retire pages for removed APIs (preview first)
/page-retire {family} {platform} --from-plan --dry-run
/page-retire {family} {platform} --from-plan

# Regenerate reference pages for modified APIs
/batch-reference {family} {platform} --update

# Sync family landing page
/family-sync {family}
```

### 3e. Monitor progress

```bash
# Record a completed step
.venv/Scripts/python scripts/pipeline/post_refresh_verify.py {family} {platform} --step "{step_name}"

# View progress
.venv/Scripts/python scripts/pipeline/post_refresh_verify.py {family} {platform} --status
```

### 3f. Verification gate

```bash
.venv/Scripts/python scripts/pipeline/post_refresh_verify.py {family} {platform} --verify
```

Runs 4 checks: (1) `stale_since` is null, (2) no content pages cite absent claim IDs,
(3) no reference pages exist for absent API classes, (4) `stale_detect.py` reports 0 stale pages.
Exit 0 = PASS (safe to commit). Exit 1 = FAIL (fix issues first).

**Note**: Retired pages (`draft: true`) still exist on disk. The verifier checks file existence,
not draft status. If the gate fails on retired pages, clear their `evidence.apis` and `evidence.claims`
to `[]` so they no longer reference removed classes.

### 3g. Recovery after failure

| Failure point | State | Recovery |
|---------------|-------|----------|
| Scout fails | Existing `merged/` preserved; `merged.bak/` cleaned | Re-run S-14 |
| Enrich fails | Continues best-effort with scout-only claims | Re-run `enrich.py` manually if needed |
| Promote fails | No delta written; `merged.bak/` cleaned | Re-run S-14 |
| Network down during fetch | `update_clone()` returns None; uses cached clone | Re-run after network restored |
| Verify gate fails | Commit blocked | Fix issues listed in output; re-run `--verify` |
| Duplicate frontmatter keys after evidence update | Pre-commit hook blocks | Deduplicate keys in affected files; re-stage |

**Verify**: `.venv/Scripts/python scripts/pipeline/audit.py {family} {platform}` — 0 FAIL expected.

## 4. Run Full Content Audit

```bash
# All products
.venv/Scripts/python scripts/pipeline/audit.py all
.venv/Scripts/python scripts/pipeline/audit.py all --json   # machine-readable

# Single product
.venv/Scripts/python scripts/pipeline/audit.py {family} {platform}

# Specific files
.venv/Scripts/python scripts/pipeline/audit.py --files path/to/file.md

# Content evaluation (multi-dimensional)
python -m scripts.pipeline.content_eval evaluate {family} {platform}

# Deep API verification
.venv/Scripts/python scripts/pipeline/truth_audit.py {family} {platform}

# Cross-platform consistency
.venv/Scripts/python scripts/pipeline/cross_platform_audit.py {family}

# Gap analysis
.venv/Scripts/python scripts/gap-eval/run.py {family} {platform} --scope docs --no-llm
```

## 5. Translate Content

```bash
# Audit existing translations
.venv/Scripts/python scripts/translator/cli.py audit --family {family} --platform {platform} --site docs.aspose.org --locales fa,es

# Translate single page
.venv/Scripts/python scripts/translator/cli.py page {file} --locales fa --dry-run
.venv/Scripts/python scripts/translator/cli.py page {file} --locales fa

# Batch translate
.venv/Scripts/python scripts/translator/cli.py batch --family {family} --platform {platform} --site docs.aspose.org --locales fa,es

# Cache stats
.venv/Scripts/python scripts/translator/cli.py cache-stats
```

**Healing loop**: audit -> translate failed pages -> re-audit -> verify improvement.

## 6. Fix Content Quality Issues

```bash
# Evaluate and auto-fix (no LLM, safe for unattended)
/batch-eval-fix {family} {platform}

# Full remediation with LLM
/batch-remediate {family} {platform}

# Fix specific category
/category-fix {family} {platform} --category ST

# Heal a single low-quality page
/heal-page {path}
```

## 7. Verify Before Committing

```bash
# Pre-commit checks (automated via hook)
.venv/Scripts/python scripts/pipeline/audit.py --files {staged-files}

# Manual verification
.venv/Scripts/python scripts/pipeline/path_guard.py {target-path}
.venv/Scripts/python scripts/pipeline/check_grade_integrity.py --files {target-files}
```

The pre-commit hook runs automatically if installed (Step 1.4).

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `audit.py` reports FAIL on API tokens | Content references API members not in knowledge model | Re-run knowledge pipeline (S3) or fix content |
| `content_eval` returns "0 pages found" | Running from wrong directory | Run from repo root: `python -m scripts.pipeline.content_eval evaluate {f} {p}` |
| `model.yaml` shows `stale_since != null` | Knowledge is outdated | Run `/knowledge-update {family} {platform}` |
| Pre-commit hook blocks commit | Staged files have API accuracy failures | Fix issues shown in hook output, re-stage |
| Translation audit finds failures | Structure drift or English leakage | Retranslate failed pages with `/translate {file} --locales {locale}` |
| `no-downgrade-guard` blocks write | Proposed content is structurally smaller than existing | Review proposed content -- likely missing sections or code blocks |
| `change-guard` blocks write | Claim references unknown format or API | Verify claim against `knowledge/{f}/{p}/merged/` artifacts |
| Grade is D or F after evaluation | Multiple quality issues | Run `/heal-page {path}` to rescue the page |
| Locale file has no `provenance:` block after clone | Pre-provenance file; backfill not run | Run `python scripts/pipeline/provenance_backfill.py` (see §1) |
| Translator sync skips a file with `auto_updatable=false` | File is explicitly protected from auto-overwrite | Intentional. To re-enable: set `auto_updatable: true` in the file's provenance block |
| `provenance_backfill.py` reports "no English source" for a file | Structural orphan (e.g., reference.aspose.org kebab-case topic pages) | These are legacy locale files with no current English counterpart. File is safe to leave; set `auto_updatable: false` to prevent accidental overwrite |

## 9. Provenance Operations

See AGENTS.md §10b for the full provenance model. Quick reference:

```bash
# Backfill provenance on files that lack it (idempotent, safe to re-run)
.venv/Scripts/python scripts/pipeline/provenance_backfill.py

# Protect a file from automated translator overwrite
# Edit the file's frontmatter:
#   provenance:
#     auto_updatable: false

# Check why a translator sync skipped a file
# Look for: [SKIP] {path} -- auto_updatable=false, requires review
python -m translator sync --family {f} --platform {p} --site docs.aspose.org --locales {locale}

# Verify provenance fields in a translated file
grep -A8 "^provenance:" content/docs.aspose.org/{locale}/{family}/{platform}/_index.md

# Check provenance coverage across a locale
grep -rn "translation_origin: translator-" content/docs.aspose.org/{locale}/{family}/{platform}/ | wc -l
```

**Provenance durability model (Option B — post-clone migration):**
- Files translated since commit `cdaa1daac`: provenance is in git, durable across clones
- Files not yet re-translated: provenance requires `provenance_backfill.py` after clone (Step 1.5)
- The backfill script is committed and idempotent. Running it is required for full provenance coverage.

## 10. Discovery: Patrol, Sweep, Triage

See `docs/discovery-workflow.md` for the full operator guide. Quick reference:

### 10a. Scan for new repos (S-93)

```bash
# Skill invocation
/repo-patrol

# Backing script — dry-run (no registry update)
.venv/Scripts/python scripts/pipeline/repo_patrol.py scan

# Apply: write discovered candidates to data/products.json
.venv/Scripts/python scripts/pipeline/repo_patrol.py scan --apply
```

Output: `reports/discovery/patrol_report.json`

### 10b. Sweep for upstream changes (S-94)

```bash
# Skill invocation
/change-sweep

# Backing script
.venv/Scripts/python scripts/pipeline/repo_patrol.py sweep
```

Output: `reports/discovery/sweep_report.json`

### 10c. Triage findings to backlog (S-95)

```bash
# Skill invocation (agent-executed, reads reports, writes backlog items)
/discovery-triage
```

**MVP rule**: S-95 NEVER directly invokes S-12 or S-84. All findings → backlog items only.
Operator reviews backlog items and manually runs `/refresh-product {family} {platform}`.

### 10d. Generate combined report

```bash
.venv/Scripts/python scripts/pipeline/repo_patrol.py report
cat reports/discovery/combined_report.md
```

### 10e. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Scan finds 0 repos | Missing `GITHUB_TOKEN` in `.env`; set and retry |
| Sweep fetch failure | Check `sweep_report.json` `fetch_failures`; verify clone URL |
| Description "pending" in provider mirror | Re-run `sync_providers.py` after adding `## Purpose` to canonical skill |
| Session advisory shows stale patrol | `patrol_report.json` > 7 days old; run `/repo-patrol` |
