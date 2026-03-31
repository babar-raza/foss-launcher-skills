# RUNBOOK — Aspose.org Operator Guide

Quick-reference for common operations. For governance rules, see `AGENTS.md`.

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

# 4. Install pre-commit hook
cp scripts/pre-commit-audit.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# 5. Populate provenance for pre-existing locale files (required post-clone migration)
# Locale files translated since cdaa1daac already have committed provenance.
# Older locale files that have not been re-translated need this step.
# The script is idempotent — safe to re-run; files with provenance are skipped.
python scripts/pipeline/provenance_backfill.py
# Expected output: "Backfilled N files, skipped M (already have provenance), 0 errors"

# 6. Verify
python scripts/pipeline/audit.py all
```

## 2. Launch a New Product

```bash
# Step 1: Bootstrap knowledge
/knowledge-bootstrap {family} {platform}

# Step 2: Generate site manifest
python scripts/pipeline/site_planner.py {family} {platform} --dry-run
# Review YAML output, then without --dry-run to write

# Step 3: Generate content (via agent skills)
/launch-product {family} {platform}
# This orchestrates: site-plan -> page generation -> evidence -> audit -> grade

# Step 4: Verify
python scripts/pipeline/audit.py {family} {platform}
python -m scripts.pipeline.content_eval evaluate {family} {platform}
python scripts/pipeline/truth_audit.py {family} {platform}
```

## 3. Refresh Knowledge After Upstream Changes

```bash
cd scripts/pipeline
python scout.py {family} {platform} ../../runs/.clone_cache/aspose_{family}_{platform}/ ../../knowledge/{family}/{platform}/scout/
python enrich.py {family} {platform}
python promote.py {family} {platform}
python index.py {family} {platform}
```

Or use the skill: `/knowledge-update {family} {platform}`

**Verify**: `python scripts/pipeline/audit.py {family} {platform}` — 0 FAIL expected.

## 4. Run Full Content Audit

```bash
# All products
python scripts/pipeline/audit.py all
python scripts/pipeline/audit.py all --json   # machine-readable

# Single product
python scripts/pipeline/audit.py {family} {platform}

# Specific files
python scripts/pipeline/audit.py --files path/to/file.md

# Content evaluation (multi-dimensional)
python -m scripts.pipeline.content_eval evaluate {family} {platform}

# Deep API verification
python scripts/pipeline/truth_audit.py {family} {platform}

# Cross-platform consistency
python scripts/pipeline/cross_platform_audit.py {family}

# Gap analysis
python scripts/gap-eval/run.py {family} {platform} --scope docs --dry-run
```

## 5. Translate Content

```bash
# Audit existing translations
python scripts/translator/cli.py audit --family {family} --platform {platform} --site docs.aspose.org --locales fa,es

# Translate single page
python scripts/translator/cli.py page {file} --locales fa --dry-run
python scripts/translator/cli.py page {file} --locales fa

# Batch translate
python scripts/translator/cli.py batch --family {family} --platform {platform} --site docs.aspose.org --locales fa,es

# Cache stats
python scripts/translator/cli.py cache-stats
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
python scripts/pipeline/audit.py --files {staged-files}

# Manual verification
python scripts/pipeline/path_guard.py {target-path}
python scripts/pipeline/check_grade_integrity.py --files {target-files}
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
python scripts/pipeline/provenance_backfill.py

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
